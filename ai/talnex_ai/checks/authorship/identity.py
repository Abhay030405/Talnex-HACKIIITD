"""Whose GitHub account counts as "ours" (architecture 30.6). TalNex says "written by GitHub account X", never "written by this person":
whether a handle belongs to someone is not checked in this version.

  Recruiter: the GitHub handle from the resume (or typed by the recruiter), else the owner of the linked repo.
  Hackathon: the team's GitHub handles from the submission form (optional); without them the card lists accounts only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from psycopg_pool import ConnectionPool

from talnex_ai.claims.store import Subject

_REPO = re.compile(r"github\.com[/:]([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?(?:[/#?]|$)", re.IGNORECASE)


def repo_of(url: Optional[str]) -> Optional[str]:
    """"owner/name" from a GitHub link, or None."""
    m = _REPO.search(url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


@dataclass(frozen=True)
class Identity:
    accounts: tuple[str, ...] = ()             # the team's accounts (hackathon), or the candidate's one account (recruiter)
    candidate: Optional[str] = None            # recruiter only: the candidate's account
    source: Optional[str] = None               # form / resume / repo_owner
    bullets: tuple[str, ...] = field(default=())   # recruiter only: the project's resume bullets, for the "I built" rule


def _clean(handle: Optional[str]) -> Optional[str]:
    h = (handle or "").strip().lstrip("@").strip()
    return h or None


def identity_of(pool: ConnectionPool, subject: Subject) -> Identity:
    with pool.connection() as conn:
        if subject.kind == "project":
            row = conn.execute("SELECT team_github_handles FROM projects WHERE id = %s::uuid", (subject.id,)).fetchone()
            handles = tuple(dict.fromkeys(h for h in (_clean(x) for x in (row[0] if row else []) or []) if h))
            return Identity(handles, None, "form" if handles else None)

        row = conn.execute(
            """SELECT cp.candidate_id::text, cp.repo_url, cp.bullets, c.coding_handles->>'github'
                 FROM candidate_projects cp JOIN candidates c ON c.id = cp.candidate_id WHERE cp.id = %s::uuid""",
            (subject.id,)).fetchone()
        if row is None:
            return Identity()
        candidate_id, repo_url, bullets, typed = row
        handle, source = _clean(typed), "resume"
        if not handle:
            # The resume reader keeps the GitHub name it found (and checked against the resume text) in its stage result.
            found = conn.execute(
                """SELECT result->>'github_username' FROM jobs
                    WHERE job_type = 'resume_read' AND target_type = 'candidate' AND target_id = %s::uuid AND status = 'done'
                    ORDER BY updated_at DESC LIMIT 1""", (candidate_id,)).fetchone()
            handle = _clean(found[0] if found else None)
        if not handle:
            repo = repo_of(repo_url)
            handle, source = (repo.split("/")[0], "repo_owner") if repo else (None, None)
    return Identity((handle,) if handle else (), handle, source if handle else None, tuple(bullets or ()))
