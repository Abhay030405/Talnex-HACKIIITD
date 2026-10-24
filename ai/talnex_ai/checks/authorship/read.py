"""Authorship read (authorship proof, A3, architecture 30.5 and 30.8). Pure functions over the history the Go stage saved.

Per claim: who wrote the feature's current lines (share per GitHub account), how it was built (commits, days spanned, the largest
single commit), and when it arrived (first and last push). Bots are left out of the shares. Commits whose email is tied to no
account are "unlinked", with no guessing by name or email. Lines owned by reformatting or moved code are never credited to whoever
reformatted or moved them. Flags are evidence only: they sit beside the score and are never subtracted from it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.checks.authorship.symbols import words_of
from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.authorship_reader import KINDS, SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json

READER_ROLE = "copy_review"     # a text model that looks only at the top commits, like the copy check's final look
UNLINKED = "unlinked"
_BOT = re.compile(r"(\[bot\]$|^dependabot|^renovate|^github-actions|^snyk-bot|^greenkeeper|^imgbot|^pre-commit-ci|^allcontributors|^web-flow$)",
                  re.IGNORECASE)
# "I built", "I implemented", "I've added", "myself": the resume speaks for one person. Capital I only, as written.
_FIRST_PERSON = re.compile(r"(?<![\w'])I(?:'ve|'d|’ve)?(?![\w'])|\bmyself\b")
_TEAM_WORDS = re.compile(r"\b(we|we've|we’ve|our|ours|us|team|teammates?|together|collaborat\w*|co-?(?:built|developed|created)|group)\b",
                         re.IGNORECASE)


def is_bot(login: Optional[str], marked: bool = False) -> bool:
    return bool(marked) or bool(login and _BOT.search(login))


def first_person(text: str) -> bool:
    """True when the text says "I built ..." (one person), and False when it says "we" or "our team" anywhere."""
    return bool(_FIRST_PERSON.search(text or "")) and not _TEAM_WORDS.search(text or "")


def matching_bullet(claim_text: str, bullets: Sequence[str]) -> Optional[str]:
    """The resume bullet a claim was read from: the one sharing the most words with it (at least two), or None."""
    words = words_of(claim_text)
    best, best_hits = None, 1
    for b in bullets:
        hits = len(words & words_of(b))
        if hits > best_hits:
            best, best_hits = b, hits
    return best


def parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def owned_lines(code_map: Sequence[Mapping[str, Any]], history_files: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """For one claim: how many of its mapped lines each commit owns (blame cut to the mapped ranges)."""
    blame = {f.get("path"): f.get("blame") or [] for f in history_files}
    owned: dict[str, int] = {}
    for r in code_map:
        start, end = int(r.get("start") or 0), int(r.get("end") or 0)
        for b in blame.get(r.get("path"), []):
            lo, hi = max(start, int(b.get("start") or 0)), min(end, int(b.get("end") or 0))
            if hi >= lo and b.get("sha"):
                owned[b["sha"]] = owned.get(b["sha"], 0) + (hi - lo + 1)
    return owned


@dataclass
class AccountShare:
    account: str
    line_share: float
    lines: int
    commits: int
    days_spanned: int
    largest_commit_share: Optional[float]
    first_pushed_at: Optional[str]
    last_pushed_at: Optional[str]
    date_source: str
    reformatted_lines: int = 0
    moved_lines: int = 0


@dataclass
class ClaimAuthorship:
    claim_id: str
    total_lines: int = 0
    accounts: list[AccountShare] = field(default_factory=list)
    original_repo_lines: int = 0      # a fork: lines from before the fork, credited to no one on the team
    reformatted_lines: int = 0
    moved_lines: int = 0
    largest_commit: Optional[str] = None
    largest_commit_share: float = 0.0
    later_edits: bool = False         # another commit touched the feature's lines after the largest one
    before_event_share: Optional[float] = None
    not_traced_reason: Optional[str] = None

    def share_of(self, account: Optional[str]) -> Optional[float]:
        if not account:
            return None
        return next((a.line_share for a in self.accounts if a.account.lower() == account.lower()), 0.0)


def _when(commit: Mapping[str, Any]) -> tuple[Optional[datetime], bool]:
    """The time a commit's lines arrived: GitHub's push time when known (it cannot be faked), else the commit time."""
    pushed = parse_time(commit.get("pushed_at"))
    return (pushed, True) if pushed else (parse_time(commit.get("committed_at")), False)


def read_claim(
    claim_id: str,
    code_map: Sequence[Mapping[str, Any]],
    history: Mapping[str, Any],
    kinds: Mapping[str, str],
    *,
    event_start: Optional[datetime] = None,
    fork_cutoff: Optional[datetime] = None,
) -> ClaimAuthorship:
    """Shares, build pattern and arrival for one claim. `kinds` says which commits were moved code or reformatting (default new)."""
    out = ClaimAuthorship(claim_id)
    commits = history.get("commits") or {}
    owned = owned_lines(code_map, history.get("files") or [])
    push_records = history.get("date_source", "push") == "push"

    per: dict[str, dict] = {}
    timed: list[tuple[str, Optional[datetime], int]] = []
    before = 0
    for sha, n in sorted(owned.items()):
        c = commits.get(sha) or {}
        if is_bot(c.get("author_login"), c.get("is_bot", False)):
            continue
        when, pushed = _when(c)
        out.total_lines += n
        if event_start and when and when < event_start:
            before += n
        if fork_cutoff and when and when < fork_cutoff:
            out.original_repo_lines += n
            continue
        account = c.get("author_login") or UNLINKED
        acc = per.setdefault(account, {"lines": 0, "reformatted": 0, "moved": 0, "shas": {}, "all_shas": set(), "times": [], "pushed": True})
        kind = kinds.get(sha, "new")
        if kind == "reformatting":
            acc["reformatted"] += n
            out.reformatted_lines += n
        elif kind == "moved":
            acc["moved"] += n
            out.moved_lines += n
        else:
            acc["lines"] += n
            acc["shas"][sha] = acc["shas"].get(sha, 0) + n
            timed.append((sha, when, n))
        acc["times"] += [when] if when else []
        acc["pushed"] = acc["pushed"] and pushed and push_records
        acc["all_shas"].add(sha)

    if out.total_lines == 0:
        out.not_traced_reason = "history not available (GitHub gave no line history for this code)"
        return out
    if event_start:
        out.before_event_share = round(before / out.total_lines, 3)

    if timed:
        sha, when, n = max(timed, key=lambda t: (t[2], t[0]))
        out.largest_commit, out.largest_commit_share = sha, round(n / out.total_lines, 3)
        out.later_edits = any(other != sha and w and when and w > when for other, w, _ in timed)

    for account, acc in per.items():
        times = sorted(acc["times"])
        largest = max(acc["shas"].values()) if acc["shas"] else 0
        out.accounts.append(AccountShare(
            account=account, line_share=round(acc["lines"] / out.total_lines, 3), lines=acc["lines"], commits=len(acc["all_shas"]),
            days_spanned=((times[-1].date() - times[0].date()).days + 1) if times else 0,
            largest_commit_share=round(largest / acc["lines"], 3) if acc["lines"] else None,
            first_pushed_at=times[0].isoformat() if times else None, last_pushed_at=times[-1].isoformat() if times else None,
            date_source="push" if acc["pushed"] else "commit", reformatted_lines=acc["reformatted"], moved_lines=acc["moved"],
        ))
    out.accounts.sort(key=lambda a: (-a.line_share, -a.reformatted_lines - a.moved_lines, a.account.lower()))
    return out


# ------------------------------------------------------------------ new, moved or reformatting (one model call per project)


class _Kind(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    sha: str = Field(min_length=4, max_length=64)
    kind: str = "new"
    reason: str = Field(default="", max_length=300)


class Kinds(BaseModel):
    model_config = ConfigDict(extra="ignore")
    commits: list[_Kind] = Field(default_factory=list, max_length=40)


def could_be_rewrite(commit: Mapping[str, Any]) -> bool:
    """Only a commit that removed about as much as it added can be moved code or reformatting; a commit that only adds is new code."""
    added, removed = int(commit.get("additions") or 0), int(commit.get("deletions") or 0)
    return added > 0 and removed >= added // 2


def top_commits(owned_total: Mapping[str, int], commits: Mapping[str, Mapping[str, Any]], limit: int) -> list[dict]:
    """The commits owning the most feature lines (bots left out) that could be moved code or reformatting, for the model."""
    ranked = sorted(owned_total.items(), key=lambda t: (-t[1], t[0]))
    out = []
    for sha, n in ranked[:limit]:
        c = commits.get(sha) or {}
        if is_bot(c.get("author_login"), c.get("is_bot", False)) or not could_be_rewrite(c):
            continue
        out.append({"sha": sha, "message": (c.get("message") or "")[:200], "additions": c.get("additions", 0),
                    "deletions": c.get("deletions", 0), "files_changed": c.get("files_changed", 0), "owned_lines": n})
    return out


def classify(model: ChatClient, candidates: Sequence[dict], *, job_id: Optional[str] = None) -> dict[str, str]:
    """One low-temperature call: which of these commits were moved code or reformatting. Unknown shas and kinds are ignored."""
    if not candidates:
        return {}
    shown = {c["sha"] for c in candidates}
    answer = ask_json(model, READER_ROLE, SYSTEM, build_user(candidates), lambda text: parse_model(Kinds, text),
                      job_id=job_id, max_tokens=1500, temperature=0.0)
    return {k.sha: k.kind for k in answer.commits if k.sha in shown and k.kind in KINDS and k.kind != "new"}


# ------------------------------------------------------------------ flags (30.8)


@dataclass(frozen=True)
class Finding:
    flag_type: str
    level: str
    reason: str
    evidence: dict


@dataclass(frozen=True)
class Thresholds:
    one_drop_share: float
    before_event_review: float
    before_event_strong: float
    claimed_min_share: float
    reformat_share: float


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def flags_for(claim_text: str, importance: int, ca: ClaimAuthorship, t: Thresholds, *,
              said_i_built: bool = False, candidate: Optional[str] = None) -> list[Finding]:
    """The authorship flags for one claim. Arrived-in-one-drop alone is Info only; with built-before-event it joins that one flag."""
    if ca.not_traced_reason or ca.total_lines == 0:
        return []
    out: list[Finding] = []
    base = {"claim_id": ca.claim_id, "total_lines": ca.total_lines}
    one_drop = ca.largest_commit is not None and ca.largest_commit_share >= t.one_drop_share and not ca.later_edits
    drop_note = (f"; {_pct(ca.largest_commit_share)} of it arrived in one commit with no later edits" if one_drop else "")

    before = ca.before_event_share or 0.0
    level = None
    if before > t.before_event_strong and importance == 3:
        level = "strong"
    elif before > t.before_event_review:
        level = "review"
    if level:
        out.append(Finding("feature_before_event", level,
                           f'Feature built before event: {_pct(before)} of the lines of "{claim_text}" were first pushed before the event started{drop_note}',
                           {**base, "before_event_share": before, "one_drop": one_drop, "largest_commit": ca.largest_commit,
                            "largest_commit_share": ca.largest_commit_share}))
    elif one_drop:
        out.append(Finding("feature_one_drop", "info",
                           f'Feature arrived in one drop: {_pct(ca.largest_commit_share)} of the lines of "{claim_text}" came in a single commit '
                           "with no later edits. Many honest people write elsewhere and push once.",
                           {**base, "largest_commit": ca.largest_commit, "largest_commit_share": ca.largest_commit_share}))

    if said_i_built and candidate:
        share = ca.share_of(candidate) or 0.0
        if share < t.claimed_min_share:
            out.append(Finding("claimed_by_other_account", "review",
                               f'Claimed feature written by another account: the resume says "I built" "{claim_text}", and GitHub account '
                               f"{candidate} wrote {_pct(share)} of its lines",
                               {**base, "account": candidate, "share": share,
                                "accounts": [{"account": a.account, "line_share": a.line_share} for a in ca.accounts[:5]]}))

    reformatted = ca.reformatted_lines / ca.total_lines
    if reformatted > t.reformat_share:
        out.append(Finding("reformatting_hides_authorship", "info",
                           f'Reformatting hides authorship: {_pct(reformatted)} of the lines of "{claim_text}" are owned by reformatting '
                           "commits, so their original author is not traced",
                           {**base, "reformatted_lines": ca.reformatted_lines}))
    return out
