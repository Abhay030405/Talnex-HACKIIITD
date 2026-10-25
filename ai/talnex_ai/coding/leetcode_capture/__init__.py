"""Stage `leetcode_replay` (recruiter, candidate-level): LeetCode Code Replay paste check (architecture section 18).

Public data only, no login and no browser. LeetCode's public data endpoint (`LEETCODE_GRAPHQL_URL`) serves the contest
history and, per contest problem, the candidate's Code Replay: every editor event with its time. Event type "10" is an
external paste. Each paste is judged by its context: short or very early pastes are helper code or a personal template;
core logic pasted in one go with almost no edits after it is Medium; Medium pastes in several contests are Strong.
Evidence only, never a verdict. A replay that cannot be read is "could not check". Running it twice replaces the rows.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from talnex_ai.browser.bql import BqlError
from talnex_ai.coding.leetcode_capture.same_code import bql_neighbours, default_code, match_paste, score_of
from talnex_ai.coding.profile import HANDLE_OK
from talnex_ai.coding.store import replace_signals, save_signal
from talnex_ai.db.jobs import Job
from talnex_ai.live import for_job
from talnex_ai.settings import LeetCodeReplaySettings
from talnex_ai.storage.keys import replay_key
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services

log = logging.getLogger("talnex.coding")

SITE = "leetcode"
SUMMARY_SIGNAL = "leetcode_replay"
PASTE_SIGNAL = "leetcode_paste"
PASTE, TYPING = "10", "7"   # replay event types: 10 = external paste, 7 = typing in the editor
SNIPPET_CHARS = 200
IDLE_NOTE_SECONDS = 60

HISTORY = """
query talnexHistory($username: String!) {
  userContestRankingHistory(username: $username) {
    attended rating ranking problemsSolved finishTimeInSeconds contest { title titleSlug startTime }
  }
}""".strip()
QUESTIONS = """
query talnexQuestions($slug: String!) {
  contestQuestionList(contestSlug: $slug) { title titleSlug credit questionId }
}""".strip()
REPLAY = """
query talnexReplay($contest: String!, $question: String!, $username: String!) {
  userContestReplayEvents(contestSlug: $contest, questionSlug: $question, username: $username) { eventType eventData timestamp }
}""".strip()


class ReplayBlocked(RuntimeError):
    """The public endpoint refused or answered something unreadable: "could not check", never a mark."""


@dataclass
class Paste:
    at_s: int            # seconds after the problem was opened, so a recruiter can watch those seconds
    lines: int
    chars: int
    edits_after: int     # typing events after the paste
    idle_before_s: int   # seconds the editor was quiet just before the paste
    snippet: str
    text: str = ""       # the whole paste, for comparing with other contestants; never saved


def _seconds(ts: str) -> float:
    return datetime.fromisoformat(ts).timestamp()


def find_pastes(events: list[Mapping[str, Any]]) -> list[Paste]:
    """Every external paste in one problem's replay, in time order."""
    events = sorted(events, key=lambda e: e["timestamp"])
    if not events:
        return []
    opened = _seconds(events[0]["timestamp"])
    out = []
    for i, e in enumerate(events):
        if e.get("eventType") != PASTE:
            continue
        try:
            data = json.loads(e.get("eventData") or "{}")
        except ValueError:
            data = {}
        text = "".join(c.get("insert") or "" for c in data.get("changes") or [] if isinstance(c, Mapping)).strip()
        if not text:
            continue
        at = _seconds(e["timestamp"])
        before = _seconds(events[i - 1]["timestamp"]) if i else at
        out.append(Paste(at_s=int(at - opened), lines=text.count("\n") + 1, chars=len(text),
                         edits_after=sum(1 for x in events[i + 1:] if x.get("eventType") == TYPING),
                         idle_before_s=int(at - before), snippet=text[:SNIPPET_CHARS], text=text))
    return out


def judge(p: Paste, cfg: LeetCodeReplaySettings) -> tuple[str, str]:
    """(weight, reason) for one paste, by the section 18 table."""
    if p.lines < cfg.paste_min_lines:
        return "not_suspicious", f"a short paste ({p.lines} lines): helper code"
    if p.at_s <= cfg.template_seconds:
        return "not_suspicious", f"pasted {p.at_s}s after opening the problem: likely a personal template"
    if p.edits_after > cfg.max_edits_after:
        return "not_suspicious", f"pasted, then worked on ({p.edits_after} edits after)"
    idle = f", editor quiet for {p.idle_before_s}s just before" if p.idle_before_s >= IDLE_NOTE_SECONDS else ""
    return "medium", f"core logic pasted in one go ({p.lines} lines) with {p.edits_after} edits after{idle}"


def rating_jumps(history: list[Mapping[str, Any]]) -> dict[str, int]:
    """Rating gained in each attended contest, by contest slug (the first contest has no gain to measure)."""
    out, prev = {}, None
    for c in history or []:
        rating = c.get("rating")
        if not c.get("attended") or not isinstance(rating, (int, float)):
            continue
        if prev is not None:
            out[(c.get("contest") or {}).get("titleSlug")] = round(rating - prev)
        prev = rating
    return out


def pick_contests(history: list[Mapping[str, Any]], cfg: LeetCodeReplaySettings, now: float) -> list[Mapping[str, Any]]:
    """The last `contests` rated contests the candidate solved something in, plus any with a big rating jump, plus the
    last `contests` voided ones. Contests newer than `settle_days` are skipped (voided ones are already settled)."""
    gains = rating_jumps(history)
    done, jumps = [], []
    for c in history or []:
        if not c.get("attended"):
            continue
        if gains.get((c.get("contest") or {}).get("titleSlug"), 0) >= cfg.rating_jump:
            jumps.append(c)
        start = (c.get("contest") or {}).get("startTime") or 0
        if c.get("problemsSolved") and now - start >= cfg.settle_days * 86400:
            done.append(c)
    chosen = done[-cfg.contests:] if cfg.contests else []
    for c in jumps:
        if c in done and c not in chosen:
            chosen.append(c)
    # Contests LeetCode voided (attended, no rank, 0 solved: often its own plagiarism check). The replays are still
    # public, and they are the ones most worth reading.
    removed = [c for c in history or [] if c.get("attended") and c.get("ranking") in (0, None) and not c.get("problemsSolved")]
    for c in (removed[-cfg.contests:] if cfg.contests else []):
        if c not in chosen:
            chosen.append(c)
    return chosen


def default_post(url: str, query: str, variables: dict) -> dict:
    """POST one query to the public endpoint. Network errors are raised (the job retries); a refusal is ReplayBlocked."""
    import httpx

    resp = httpx.post(url, json={"query": query, "variables": variables}, timeout=30,
                      headers={"Content-Type": "application/json", "Referer": "https://leetcode.com/contest/", "User-Agent": "talnex"})
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200 or not isinstance(body, Mapping) or body.get("errors"):
        raise ReplayBlocked(f"the public data endpoint answered {resp.status_code}")
    return body["data"]


def _lang(events: list[Mapping[str, Any]]) -> str:
    for e in events:
        try:
            lang = json.loads(e.get("eventData") or "{}").get("lang")
        except ValueError:
            lang = None
        if lang:
            return lang
    return ""


def _same_code(r: dict, *, slug: str, events: list, score: int, finish: Optional[int], handle: str,
               cfg: LeetCodeReplaySettings, neighbours: Callable[..., list[dict]], code: Callable, near_cache: dict) -> None:
    """Compare one Medium paste with the code of the people who finished near the candidate; Strong on enough matches."""
    if finish is None:
        r["same_code"] = {"reason": "could not check: no finish time in the public history"}
        return
    qid = r["question"].get("questionId")
    try:
        if (slug, qid) not in near_cache:
            near_cache[(slug, qid)] = neighbours(slug, qid, score, finish, handle, cfg.match_pages)
    except (BqlError, ValueError, KeyError) as err:
        r["same_code"] = {"reason": f"could not check: {err}"[:200]}
        return
    found = match_paste(r["paste"].text, _lang(events), near_cache[(slug, qid)], min_pct=cfg.match_pct, code=code)
    r["same_code"] = found
    if found["matches"] >= cfg.match_min_users:
        r["weight"] = "strong"
        r["reason"] += (f"; {found['matches']} people who finished near them submitted the same code "
                        f"(at least {cfg.match_pct:g}% alike, closest {found['best_pct']:g}%)")


def check_replays(url: str, handle: str, cfg: LeetCodeReplaySettings, *, post: Callable[[str, str, dict], dict] = default_post,
                  now: Optional[float] = None, contests: Optional[list[str]] = None,
                  neighbours: Optional[Callable[..., list[dict]]] = None, code: Callable = default_code,
                  note: Callable[..., None] = lambda *a, **k: None) -> dict[str, Any]:
    """Read and judge the candidate's replays. `contests` (slugs) skips the history pick, for a manual check. With
    `neighbours` (a Browserless ranking walk), long Medium pastes are also compared with nearby contestants' code."""
    history = post(url, HISTORY, {"username": handle}).get("userContestRankingHistory") or []
    gains = rating_jumps(history)
    finishes = {(c.get("contest") or {}).get("titleSlug"): (c.get("contest") or {}).get("startTime", 0) + c["finishTimeInSeconds"]
                for c in history if c.get("attended") and isinstance(c.get("finishTimeInSeconds"), int)}
    if contests is None:
        chosen = [((c.get("contest") or {}).get("titleSlug"), (c.get("contest") or {}).get("title"))
                  for c in pick_contests(history, cfg, now if now is not None else time.time())]
    else:
        chosen = [(slug, slug) for slug in contests]
    attended = sum(1 for c in history if c.get("attended"))
    note("note", label="history", text=f"{attended} contests attended, {len(chosen)} picked to read")

    pastes, checked, replays, kept, near_cache = [], [], 0, {}, {}
    for slug, title in chosen:
        if not slug:
            continue
        questions = post(url, QUESTIONS, {"slug": slug}).get("contestQuestionList") or []
        checked.append(title or slug)
        contest_pastes, contest_replays = [], {}
        for q in questions:
            events = post(url, REPLAY, {"contest": slug, "question": q["titleSlug"], "username": handle}).get("userContestReplayEvents")
            if not events:
                continue   # not attempted, or no replay kept
            replays += 1
            kept[(slug, q["titleSlug"])] = contest_replays[q["titleSlug"]] = events
            for p in find_pastes(events):
                weight, reason = judge(p, cfg)
                contest_pastes.append({"contest": title or slug, "contest_slug": slug, "problem": q.get("title") or q["titleSlug"],
                               "problem_slug": q["titleSlug"], "rating_jump": gains.get(slug), "weight": weight,
                               "reason": reason, "paste": p, "question": q})
        if neighbours is not None:
            score = score_of(contest_replays, {q["titleSlug"]: q.get("credit") or 0 for q in questions})
            for r in contest_pastes:
                if r["weight"] == "medium" and r["paste"].lines >= cfg.match_min_lines:
                    _same_code(r, slug=slug, events=contest_replays[r["problem_slug"]], score=score, finish=finishes.get(slug),
                               handle=handle, cfg=cfg, neighbours=neighbours, code=code, near_cache=near_cache)
        pastes += contest_pastes
        odd = sum(1 for r in contest_pastes if r["weight"] != "not_suspicious")
        note("note", label="contest", text=f"{title or slug}: {len(contest_replays)} replays read, {len(contest_pastes)} pastes"
                                         + (f", {odd} suspicious" if odd else ""))

    suspicious_contests = {r["contest_slug"] for r in pastes if r["weight"] == "medium"}
    if len(suspicious_contests) >= cfg.repeat_contests:
        for r in pastes:
            if r["weight"] == "medium":
                r["weight"] = "strong"
                r["reason"] += f"; the pattern repeats in {len(suspicious_contests)} contests"
    # the full replay of every problem with a suspicious paste, so a recruiter can watch it later
    flagged = {(r["contest_slug"], r["problem_slug"]) for r in pastes if r["weight"] != "not_suspicious"}
    return {"contests_checked": checked, "replays_read": replays, "pastes": pastes,
            "flagged_replays": {k: kept[k] for k in flagged},
            "suspicious": sum(1 for r in pastes if r["weight"] != "not_suspicious")}


def _paste_row(r: Mapping[str, Any], saved: Mapping[tuple, str]) -> dict[str, Any]:
    p: Paste = r["paste"]
    return {"weight": r["weight"], "contest": r["contest"], "problem": r["problem"], "replay_time_s": p.at_s,
            "evidence": {"reason": r["reason"], "at": f"{p.at_s // 60:02d}:{p.at_s % 60:02d}", "lines": p.lines,
                         "chars": p.chars, "edits_after": p.edits_after, "idle_before_s": p.idle_before_s,
                         "snippet": p.snippet, "ranking_url": f"https://leetcode.com/contest/{r['contest_slug']}/ranking/",
                         "rating_jump": r.get("rating_jump"), "same_code": r.get("same_code"),
                         "replay_key": saved.get((r["contest_slug"], r["problem_slug"]))}}


@stage("leetcode_replay")
def leetcode_replay(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    if job.target_type != "candidate":
        raise ValueError(f"the leetcode_replay stage works on a candidate, not a {job.target_type!r}")
    cfg = get_services(ctx.pool).cfg
    url = getattr(cfg, "leetcode_graphql_url", "") if cfg else ""
    if not url:
        return {"skipped": True, "reason": "LEETCODE_GRAPHQL_URL is not set"}
    with ctx.pool.connection() as conn:
        row = conn.execute("SELECT coding_handles->>'leetcode' FROM candidates WHERE id = %s::uuid", (job.target_id,)).fetchone()
    if row is None:
        raise LookupError(f"candidate {job.target_id} does not exist")
    handle = (row[0] or "").strip()
    if not handle:
        return {"skipped": True, "reason": "no leetcode handle was given"}
    if not HANDLE_OK.match(handle):
        return {"found": False, "handle": handle[:60], "reason": "the leetcode handle has characters a profile name cannot have"}

    try:
        near = bql_neighbours(cfg.browserless_bql_url, cfg.browserless_token) \
            if cfg.browserless_bql_url and cfg.browserless_token else None   # off: pastes are judged on the replay alone
        result = check_replays(url, handle, cfg.leetcode_replay, neighbours=near, note=for_job(ctx.pool, job))
    except ReplayBlocked as err:
        replace_signals(ctx.pool, job.target_id, SITE, PASTE_SIGNAL, [])
        replace_signals(ctx.pool, job.target_id, SITE, SUMMARY_SIGNAL, [])
        return {"handle": handle, "found": False, "reason": f"the replays could not be read ({err})"}
    ctx.check()

    saved = {}
    files = get_services(ctx.pool).files
    for (contest, problem), events in result["flagged_replays"].items():
        key = replay_key(job.target_id, contest, problem)
        try:
            files.put_bytes(key, json.dumps(events).encode(), "application/json")
            saved[(contest, problem)] = key
        except Exception as err:  # the paste row still stands, just without its saved replay
            log.warning("could not save replay %s: %s", key, err)
    flagged = [r for r in result["pastes"] if r["weight"] != "not_suspicious"]
    replace_signals(ctx.pool, job.target_id, SITE, PASTE_SIGNAL, [_paste_row(r, saved) for r in flagged])
    save_signal(ctx.pool, job.target_id, SITE, SUMMARY_SIGNAL, {
        "handle": handle, "contests_checked": result["contests_checked"], "replays_read": result["replays_read"],
        "pastes": len(result["pastes"]), "suspicious_pastes": len(flagged), "source": "public Code Replay data"})
    return {"handle": handle, "found": True, "contests_checked": len(result["contests_checked"]),
            "replays_read": result["replays_read"], "pastes": len(result["pastes"]), "suspicious_pastes": len(flagged)}
