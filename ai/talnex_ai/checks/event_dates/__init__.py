"""Turns the facts of the Go `event_dates` stage into red flags (architecture sections 12 and 17). Pure functions.

Commit dates can be set by whoever made the commit, and honest teams sometimes start from their own template, so a
flag is a reason for a judge to look, never a verdict. The only "strong" case needs GitHub's own record of when the
repository was created, which the team cannot change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

REVIEW_ABOVE_PCT = 30.0
STRONG_ABOVE_PCT = 60.0


@dataclass(frozen=True)
class DateFlag:
    flag_type: str
    level: str      # info / review / strong
    reason: str
    evidence: dict


def date_flags(facts: Mapping[str, Any]) -> list[DateFlag]:
    """Flags for one project from the `event_dates` stage result. Nothing to say gives an empty list."""
    if not facts or not facts.get("found") or facts.get("empty"):
        return []
    flags: list[DateFlag] = []
    share: Optional[float] = facts.get("share_before_start_pct")
    created_before = bool(facts.get("repo_created_before_start"))
    if share is not None and share > REVIEW_ABOVE_PCT:
        level = "strong" if share > STRONG_ABOVE_PCT and created_before else "review"
        flags.append(DateFlag(
            "code_before_event", level,
            f"{round(share)}% of the final code already existed before the event started",
            {
                "share_before_start_pct": share, "repo_created_before_start": created_before,
                "repo_created_at": facts.get("repo_created_at"), "event_starts_at": facts.get("starts_at"),
                "last_commit_before_start": facts.get("last_commit_before_start"),
                "files": facts.get("files"), "files_before_start": facts.get("files_before_start"),
                "note": "Commit dates can be set by their author; the repository creation date is GitHub's own record. "
                        "Libraries, build output and pictures are not counted.",
                "tree_truncated": bool(facts.get("tree_truncated")),
            },
        ))
    if facts.get("one_big_upload"):
        flags.append(DateFlag(
            "one_big_upload", "info",
            "All the code was pushed in one go close to the deadline",
            {"commits_read": facts.get("commits_read"), "repo_created_at": facts.get("repo_created_at"),
             "note": "Honest teams sometimes upload everything at the end."},
        ))
    return flags
