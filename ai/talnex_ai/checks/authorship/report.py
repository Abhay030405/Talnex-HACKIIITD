"""The authorship part of the proof card and the recruiter report (architecture 30.7). Pure code: reads saved rows, no model calls.

Each claim gets an "authorship" object (where the code is, which accounts wrote it, a one-line summary), and a hackathon card gets a
"who_built_what" list: each account against the features it wrote most of, with no percentages and no ranking."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from talnex_ai.checks.authorship.identity import identity_of
from talnex_ai.checks.authorship.read import UNLINKED
from talnex_ai.checks.authorship.store import authorship_rows, code_map_row
from talnex_ai.claims.store import Subject

_COLUMN = {"project": "project_id", "candidate_project": "candidate_project_id"}
_PIPELINE = {"project": "hackathon", "candidate_project": "recruiter"}
_NOT_TRACED_DEFAULT = "no code map was made for this claim"


def _latest_result(conn, kind: str, subject_id: str, job_type: str) -> dict:
    row = conn.execute(
        """SELECT result FROM jobs WHERE pipeline = %s AND job_type = %s AND target_type = %s AND target_id = %s::uuid
              AND status = 'done' ORDER BY updated_at DESC LIMIT 1""", (_PIPELINE[kind], job_type, kind, subject_id)).fetchone()
    return (row[0] if row and isinstance(row[0], dict) else None) or {}


def blob_url(repo: str, sha: str, path: str, start: int, end: int) -> str:
    return f"https://github.com/{repo}/blob/{sha}/{path}#L{start}-L{end}"


def _day(value: Optional[str]) -> str:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    return f"{d.day} {d.strftime('%b')}"


def summary_line(accounts: list[dict]) -> str:
    """"82% written by @acc, 14 commits over 19 days, first pushed 3 Mar (GitHub records)" for the account with the biggest share."""
    top = accounts[0]
    who = "an unlinked author (no GitHub account)" if top["account"] == UNLINKED else f"@{top['account']}"
    commits, days = top["commits"], top["days_spanned"]
    text = f"{round(top['line_share'] * 100)}% written by {who}, {commits} commit{'s' if commits != 1 else ''} over {days} day{'s' if days != 1 else ''}"
    first = _day(top.get("first_pushed_at"))
    if first:
        text += f", first pushed {first}"
    return text + (" (GitHub records)" if top["date_source"] == "push" else " (commit dates only: push dates were not available)")


def claim_authorship(conn, claim_id: str, repo: Optional[str], candidate: Optional[str]) -> Optional[dict]:
    """The "authorship" object of one claim, or None when the stage never saw it (the older cards stay as they were)."""
    cmap = code_map_row(conn, claim_id)
    if cmap is None:
        return None
    sha = cmap["commit_sha"]
    rows = authorship_rows(conn, claim_id)
    reason = cmap["not_traced_reason"]
    if not reason and not rows:
        reason = "history not available (the history stage gave no lines for this code)" if sha else _NOT_TRACED_DEFAULT
    base: dict[str, Any] = {"status": "not_traced" if reason else "traced", "reason": reason, "repo": repo, "commit_sha": sha,
                            "files": [], "accounts": [], "summary": None, "candidate_share": None}
    if repo and sha:
        base["files"] = [{"path": f["path"], "start": f["start"], "end": f["end"],
                         "url": blob_url(repo, sha, f["path"], f["start"], f["end"])} for f in cmap["files"]]
    if reason:
        return base
    base["accounts"] = [{k: a[k] for k in ("account", "line_share", "lines", "commits", "days_spanned", "first_pushed_at",
                                          "last_pushed_at", "date_source")} for a in rows]
    base["summary"] = summary_line(base["accounts"])
    if candidate:
        base["candidate_share"] = next((a["line_share"] for a in rows if a["account"].lower() == candidate.lower()), 0.0)
    return base


def attach(pool_conn, kind: str, subject_id: str, feats: list[dict], *, candidate: Optional[str] = None) -> dict[str, Any]:
    """Add "authorship" to every feature (in place). Returns the repo and the candidate account that were used."""
    repo = (_latest_result(pool_conn, kind, subject_id, "authorship_read").get("repo")
            or _latest_result(pool_conn, kind, subject_id, "code_locate").get("repo")
            or _latest_result(pool_conn, kind, subject_id, "github_check").get("repo"))
    for f in feats:
        f["authorship"] = claim_authorship(pool_conn, f["claim_id"], repo, candidate)
    return {"repo": repo, "candidate": candidate}


def candidate_account(pool, subject_id: str) -> Optional[str]:
    return identity_of(pool, Subject("candidate_project", subject_id)).candidate


def who_built_what(feats: list[dict], team_accounts: list[str]) -> list[dict]:
    """Each team account against the features it wrote most of (it is the top account of that feature). No percentages, no ranking:
    accounts are listed in the order the team gave them, features in claim order. Without team handles, the top account of each feature."""
    wanted = {a.lower(): a for a in team_accounts}
    by_account: dict[str, list[str]] = {a: [] for a in team_accounts}
    for f in feats:
        au = f.get("authorship") or {}
        if au.get("status") != "traced" or not au.get("accounts"):
            continue
        top = au["accounts"][0]["account"]
        if top == UNLINKED:
            continue
        if wanted and top.lower() not in wanted:
            continue
        key = wanted.get(top.lower(), top)
        by_account.setdefault(key, []).append(f["text"])
    return [{"account": a, "features": texts} for a, texts in by_account.items() if texts]
