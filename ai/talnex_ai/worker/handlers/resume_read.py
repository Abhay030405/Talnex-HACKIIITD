"""Stage `resume_read` (recruiter, one per candidate): read the resume, save what it lists, then wait for the recruiter.

The resume is read once, here, and nothing else touches the file. The text is never saved; only the projects,
links, bullets and coding handles and profile links are. A project already saved from an earlier read is updated,
not added twice. The candidate then waits in `awaiting_confirmation`: the recruiter checks what was found, and the
Go API (`POST /v1/candidates/{id}/confirm`) starts the project and coding checks.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.db.jobs import Job
import logging

from talnex_ai.reports.ask_tools import GitHubReader
from talnex_ai.resume.extract import ResumeError, pdf_text
from talnex_ai.resume.github_match import fill_missing_repos
from talnex_ai.resume.reader import read_resume
from talnex_ai.resume.store import save_resume
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services

log = logging.getLogger("talnex.resume_read")


def _github_user(found) -> str | None:
    if found.github_username:
        return found.github_username
    link = (found.profile_links or {}).get("github") or ""
    parts = link.split("github.com/", 1)[-1].strip("/").split("/") if "github.com/" in link else []
    return parts[0] if parts and parts[0] else None


def _find_missing_repos(sv, found) -> list[str]:
    """Projects with no repository link: look for them on the person's own GitHub. Never fails the read."""
    user = _github_user(found)
    if not user or all(p.repo_url for p in found.projects):
        return []
    try:
        repos = GitHubReader(sv.cfg.github_api_base_url, sv.cfg.github_token).user_repos(user)
    except Exception as err:  # GitHub down or rate limited: the recruiter can still add the link by hand
        log.warning("could not list %s's repositories: %s", user, err)
        return []
    found.projects, filled = fill_missing_repos(found.projects, repos)
    return filled


def _set_candidate(pool, candidate_id: str, status: str, detail: str | None = None) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE candidates SET status = %s, status_detail = %s, updated_at = now() WHERE id = %s::uuid",
                     (status, detail, candidate_id))


@stage("resume_read")
def resume_read(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    candidate_id = job.target_id
    with ctx.pool.connection() as conn:
        row = conn.execute("SELECT resume_key FROM candidates WHERE id = %s::uuid", (candidate_id,)).fetchone()
    if row is None:
        raise LookupError(f"candidate {candidate_id} does not exist")
    if not row[0]:
        _set_candidate(ctx.pool, candidate_id, "failed", "No resume was uploaded")
        raise ValueError("this candidate has no resume file")

    _set_candidate(ctx.pool, candidate_id, "reading")
    try:
        text = pdf_text(sv.files.get_bytes(row[0]))
    except ResumeError as exc:
        _set_candidate(ctx.pool, candidate_id, "failed", f"The resume could not be read: {exc}")
        raise
    ctx.check()

    found = read_resume(sv.model, text, job_id=job.id)
    for finding in found.findings:
        if finding.level in ("strong", "review"):
            add_flag(ctx.pool, "candidate", candidate_id, "hidden_ai_instructions", finding.level,
                     "Text aimed at an AI checker was found in the resume", finding.as_flag_evidence())
    repos_found = _find_missing_repos(sv, found)
    # Nothing is tested yet. The recruiter sees what was found and confirms it; the Go API starts the checks then.
    ids = save_resume(ctx.pool, candidate_id, found)
    _set_candidate(ctx.pool, candidate_id, "awaiting_confirmation")
    return {
        "projects": len(ids), "candidate_project_ids": ids,
        "coding_handles": sorted(found.coding_handles), "github_username": found.github_username,
        "repos_found_on_github": repos_found, "dropped": found.dropped, "hidden_instruction_findings": len(found.findings),
    }
