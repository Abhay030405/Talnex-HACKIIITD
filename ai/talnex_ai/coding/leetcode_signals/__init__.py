"""Stage `leetcode` (recruiter, candidate-level): public LeetCode profile facts. Evidence only, never a verdict.

Public data only, no login. When `LEETCODE_GRAPHQL_URL` is set it reads LeetCode's own public data endpoint (the same
no-login JSON the profile page loads): solved counts, contest rating, and the contest history, which can show a contest
the user joined but has no standing in (a voided result). Otherwise it reads the public profile page through Fetch. The
logged-in Code Replay capture and paste analysis are not built (see `coding/leetcode_capture/`). Running it twice
replaces the rows.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional

from talnex_ai.coding.leetcode_signals import graphql
from talnex_ai.coding.profile import HANDLE_OK, first_number, run_profile
from talnex_ai.coding.store import clear_signal, save_signal
from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services

log = logging.getLogger("talnex.coding")

SITE = "leetcode"
SIGNAL = "leetcode_profile"
REMOVED_SIGNAL = "leetcode_removed_contest"
FIELDS = {
    "solved_total": "total problems solved", "solved_easy": "easy problems solved", "solved_medium": "medium problems solved",
    "solved_hard": "hard problems solved", "contest_rating": "contest rating", "contests_attended": "contests attended",
    "global_ranking": "global ranking", "submissions_past_year": "submissions in the past year",
    "active_days": "total active days", "max_streak": "max streak in days",
}


def profile_url(handle: str) -> str:
    return f"https://leetcode.com/u/{handle}/"


def _solved(word: str, text: str):
    return first_number([rf"\b{word}\b[:\s]*(\d+)\s*/\s*\d+", rf"\b{word}\b[:\s]+(\d+)\b"], text)


def parse_profile(text: str) -> dict[str, Any]:
    """Plain-code reading of the fetched page text. Returns only what it can see; {} if the layout is not recognised."""
    facts = {
        "solved_total": first_number([r"\bSolved\b[:\s]*(\d+)\s*/\s*\d+", r"(\d+)\s*/\s*\d+\s*\n?\s*Solved\b",
                                      r"Total Solved[:\s]*(\d+)"], text),
        "solved_easy": _solved("Easy", text), "solved_medium": _solved("Med(?:ium)?", text), "solved_hard": _solved("Hard", text),
        "contest_rating": first_number([r"Contest Rating[:\s]*([\d,]+(?:\.\d+)?)"], text, as_float=True),
        "contests_attended": first_number([r"Attended[:\s]*(\d+)", r"Contests? Attended[:\s]*(\d+)"], text),
        "global_ranking": first_number([r"Global Ranking[:\s]*([\d,]+)"], text),
        "submissions_past_year": first_number([r"([\d,]+)\s+submissions? in the past one year"], text),
        "active_days": first_number([r"Total Active Days[:\s]*(\d+)"], text),
        "max_streak": first_number([r"Max Streak[:\s]*(\d+)"], text),
    }
    if facts["contest_rating"] is not None and facts["contest_rating"] == int(facts["contest_rating"]):
        facts["contest_rating"] = int(facts["contest_rating"])
    keep = {k: v for k, v in facts.items() if v is not None}
    return keep if {"solved_total", "solved_easy", "solved_medium", "solved_hard", "contest_rating", "submissions_past_year"} & keep.keys() else {}


def _default_post(url: str, handle: str):
    """POST the query to the public endpoint. Returns (status_code, json_or_None). Raises on a network/budget problem."""
    import httpx

    headers = {"Content-Type": "application/json", "Referer": f"https://leetcode.com/u/{handle}/",
               "User-Agent": "talnex"}
    resp = httpx.post(url, json={"query": graphql.QUERY, "variables": {"username": handle}}, headers=headers, timeout=20)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


def read_graphql(url: str, handle: str, post: Callable[[str, str], tuple] = _default_post) -> tuple[str, Optional[dict]]:
    """('ok', facts) / ('not_found', None) / ('blocked', reason). Network and budget errors are raised, so the job retries."""
    status, payload = post(url, handle)
    if status != 200 or not isinstance(payload, Mapping):
        return "blocked", f"the public data endpoint answered {status} (it may be rate-limiting or challenging us)"
    facts = graphql.facts_from_payload(payload)
    if facts is None:
        return "not_found", None
    return "ok", facts


def _handle(job: Job, ctx: JobContext) -> Optional[str]:
    with ctx.pool.connection() as conn:
        row = conn.execute("SELECT coding_handles->>'leetcode' FROM candidates WHERE id = %s::uuid", (job.target_id,)).fetchone()
    if row is None:
        raise LookupError(f"candidate {job.target_id} does not exist")
    return (row[0] or "").strip()


@stage("leetcode")
def leetcode(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    if job.target_type != "candidate":
        raise ValueError(f"the leetcode stage works on a candidate, not a {job.target_type!r}")
    cfg = get_services(ctx.pool).cfg
    url = getattr(cfg, "leetcode_graphql_url", "") if cfg else ""
    if not url:
        return run_profile(job, ctx, site=SITE, signal=SIGNAL, url_for=profile_url, parse=parse_profile, fields=FIELDS)

    handle = _handle(job, ctx)
    if not handle:
        return {"skipped": True, "reason": "no leetcode handle was given"}
    if not HANDLE_OK.match(handle):
        return {"found": False, "handle": handle[:60], "reason": "the leetcode handle has characters a profile name cannot have"}

    outcome, facts = read_graphql(url, handle)
    ctx.check()
    base = {"handle": handle, "profile_url": profile_url(handle)}
    if outcome != "ok":
        clear_signal(ctx.pool, job.target_id, SITE, SIGNAL)
        clear_signal(ctx.pool, job.target_id, SITE, REMOVED_SIGNAL)
        reason = "this LeetCode user does not exist" if outcome == "not_found" else \
            f"the public data could not be read ({facts if isinstance(facts, str) else 'blocked'})"
        return {**base, "found": False, "reason": reason}

    removed = facts.pop("removed_contests", [])
    save_signal(ctx.pool, job.target_id, SITE, SIGNAL, {**base, **facts, "source": "public data endpoint"})
    if removed:
        save_signal(ctx.pool, job.target_id, SITE, REMOVED_SIGNAL,
                    {**base, "removed_contests": removed, "count": len(removed)}, weight="medium")
    else:
        clear_signal(ctx.pool, job.target_id, SITE, REMOVED_SIGNAL)
    return {**base, "found": True, "facts": facts, "removed_contests": len(removed)}
