"""What a stage handler needs to know about the thing it's working on.

A handler works for both kinds of subject: a hackathon `project` and a recruiter
`candidate_project`. It never asks which mode it's in; this module turns a job's target into one
plain description, whichever table it comes from.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

from psycopg_pool import ConnectionPool

from talnex_ai.claims.store import Subject
from talnex_ai.db.jobs import Job
from talnex_ai.formats import RoleLevel

SubjectKind = Literal["project", "candidate_project"]


@dataclass(frozen=True)
class SubjectInfo:
    subject: Subject
    name: str
    live_url: Optional[str]
    repo_url: Optional[str]
    video_url: Optional[str]
    role_level: RoleLevel
    brief: str = ""      # what the recruiter is hiring for (the role), as plain text for prompts; data, never orders

    @property
    def kind(self) -> str:
        return self.subject.kind

    @property
    def id(self) -> str:
        return self.subject.id

    @property
    def live_host(self) -> str:
        """The live link's host name, used to tie sign-up details and emails to the site."""
        if not self.live_url:
            return ""
        url = self.live_url if "//" in self.live_url else "https://" + self.live_url
        return (urlparse(url).hostname or "").lower()


_QUERIES = {
    "project": """SELECT p.team_name, p.live_url, p.repo_url, p.video_url, e.role_level, NULL, e.brief, p.abstract
                    FROM projects p JOIN events e ON e.id = p.event_id WHERE p.id = %s::uuid""",
    "candidate_project": """SELECT cp.name, cp.live_url, cp.repo_url, cp.video_url, c.role_level, c.role_id::text, '', ''
                    FROM candidate_projects cp JOIN candidates c ON c.id = cp.candidate_id WHERE cp.id = %s::uuid""",
}

# The project status the website shows while stages run. Only hackathon projects have one.
PROJECT_STATUSES = {"submitted", "prechecking", "reading", "testing", "checking", "scoring", "done", "done_with_gaps"}


def subject_of(job: Job) -> Subject:
    if job.target_type not in _QUERIES:
        raise ValueError(f"this stage works on a project or a candidate_project, not a {job.target_type!r}")
    return Subject(job.target_type, job.target_id)  # type: ignore[arg-type]


def load_subject_info(pool: ConnectionPool, subject: Subject) -> SubjectInfo:
    with pool.connection() as conn:
        row = conn.execute(_QUERIES[subject.kind], (subject.id,)).fetchone()
        if row is None:
            raise LookupError(f"{subject.kind} {subject.id} does not exist")
        name, live_url, repo_url, video_url, role_level, role_id, event_brief, abstract = row
        brief = role_brief(conn, role_id) if role_id else "\n".join(
            part for part in (f"Event brief: {event_brief[:4000]}" if event_brief else "",
                              f"The team's abstract: {abstract[:2000]}" if abstract else "") if part)
    return SubjectInfo(subject, name or "", _blank_to_none(live_url), _blank_to_none(repo_url),
                       _blank_to_none(video_url), role_level, brief)


def role_brief(conn, role_id: str) -> str:
    """The role as short plain text: title, job description, the person wanted, skills and criteria."""
    row = conn.execute("SELECT title, job_description, person_wanted, skills FROM roles WHERE id = %s::uuid", (role_id,)).fetchone()
    if row is None:
        return ""
    title, jd, person, skills = row
    criteria = conn.execute("SELECT name, weight FROM criteria WHERE role_id = %s::uuid ORDER BY weight DESC", (role_id,)).fetchall()
    parts = [f"Role: {title}"]
    if skills:
        parts.append("Must-have skills: " + ", ".join(skills))
    if criteria:
        parts.append("What matters most (weight): " + ", ".join(f"{n} ({float(w):g})" for n, w in criteria))
    if person:
        parts.append(f"The person wanted: {person}")
    if jd:
        parts.append(f"Job description: {jd[:4000]}")
    return "\n".join(parts)


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    """An empty or space-only link from a form means "no link", not a link to test."""
    return value.strip() if value and value.strip() else None


def set_status(pool: ConnectionPool, info: SubjectInfo, status: str) -> None:
    """Show progress on the website. Only hackathon projects carry a status; for a resume project this does nothing."""
    if info.kind != "project":
        return
    if status not in PROJECT_STATUSES:
        raise ValueError(f"unknown project status {status!r}")
    with pool.connection() as conn:
        conn.execute("UPDATE projects SET status = %s, updated_at = now() WHERE id = %s::uuid", (status, info.id))


def stage_result(pool: ConnectionPool, job: Job, stage: str) -> Optional[dict]:
    """The saved result of an earlier stage in the same pipeline, target and run, or None if it hasn't finished."""
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT result FROM jobs
                WHERE pipeline IS NOT DISTINCT FROM %s AND target_type = %s AND target_id = %s::uuid
                  AND run_number = %s AND job_type = %s AND status = 'done'
                ORDER BY updated_at DESC LIMIT 1""",
            (job.pipeline, job.target_type, job.target_id, job.run_number, stage),
        ).fetchone()
    return row[0] if row else None


def job_started_at(pool: ConnectionPool, job: Job):
    """When the job was queued (a timestamp from the database)."""
    with pool.connection() as conn:
        return conn.execute("SELECT created_at FROM jobs WHERE id = %s::uuid", (job.id,)).fetchone()[0]
