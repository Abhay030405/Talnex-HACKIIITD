"""Stage `claims`: turn what a project promises into testable claims.

One stage name for every kind of subject; where the claims come from differs:
- a fixed-problem hackathon project: the organizer's weighted criteria,
- an open-theme hackathon project: the features its code really implements (read in a sandbox VM),
- a project on a resume: its bullets, then the README of its repository.

A re-run keeps the claims of the first run, so the two runs test the same things and can be compared.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from talnex_ai.claims.criteria import claims_from_criteria, load_brief
from talnex_ai.claims.from_code import find_features
from talnex_ai.claims.resume_claims import claims_from_resume
from talnex_ai.claims.store import Subject, load_claims, save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.stack_detect.gather import RepoUnreachable, clone, read_facts
from talnex_ai.sandbox.stack_detect.recipe import FULL_IMAGE
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import load_subject_info, subject_of


def _reused(sv, subject: Subject, job: Job, sources: tuple[str, ...]) -> dict | None:
    """The claims of an earlier run, if there are any, with the test hints that run saved."""
    saved = [c for c in load_claims(sv.pool, subject) if c.source in sources]
    if not saved:
        return None
    with sv.pool.connection() as conn:
        row = conn.execute(
            """SELECT result->'notes' FROM jobs WHERE job_type = 'claims' AND target_type = %s AND target_id = %s::uuid
                  AND status = 'done' AND result ? 'notes' ORDER BY updated_at DESC LIMIT 1""",
            (job.target_type, job.target_id)).fetchone()
    out: dict[str, Any] = {"claims": len(saved), "reused": True}
    if row and row[0]:
        out["notes"] = row[0]   # the test planner reads these hints from this run's result
    return out


def project_claims(sv, subject: Subject, job: Job) -> Mapping[str, Any]:
    """Hackathon project: the organizer's criteria (fixed problem) or its own code (open theme)."""
    brief = load_brief(sv.pool, subject.id)
    if brief is None:
        raise LookupError(f"project {subject.id} does not exist")
    if brief.mode != "fixed_problem":
        return claims_from_code(sv, subject, job)
    earlier = _reused(sv, subject, job, ("criteria",))
    if earlier:
        return earlier
    out = claims_from_criteria(sv.model, brief, job_id=job.id)
    kept = save_claims(sv.pool, subject, out.claims)
    return {"claims": len(kept), "testable": sum(1 for c in kept if c.testable), "reused": False}


def claims_from_code(sv, subject: Subject, job: Job) -> Mapping[str, Any]:
    """Open-theme project: the features its code implements, each with a hint on how to try it live."""
    earlier = _reused(sv, subject, job, ("code",))
    if earlier:
        return earlier
    info = load_subject_info(sv.pool, subject)
    if not info.repo_url:
        return {"skipped": True, "reason": "no repository link was given, so no features could be read from code"}
    if sv.sandbox is None or not sv.cfg.sandbox.enabled:
        return {"skipped": True, "reason": "the sandbox host is not set up, so the code could not be read"}
    cfg = sv.cfg.sandbox
    vm = sv.sandbox.open_vm(FULL_IMAGE)   # a host that is down or full raises, and the queue tries again
    try:
        clone(vm, info.repo_url)
        facts = read_facts(vm)
        readme = next((text for path, text in facts.texts.items() if path.lower().startswith("readme")), "")
        found = find_features(sv.model, vm, info.name, facts.files, readme=readme, live_url=info.live_url or "",
                              max_files=cfg.feature_read_max_files, max_kb=cfg.feature_read_max_kb,
                              max_claims=cfg.feature_max_claims, job_id=job.id)
    except RepoUnreachable as err:
        return {"skipped": True, "reason": f"the repository could not be read: {err}"}
    finally:
        vm.destroy()
    kept = save_claims(sv.pool, subject, found.claims)
    return {"claims": len(kept), "testable": sum(1 for c in kept if c.testable), "reused": False,
            "files_read": found.files_read, "dropped_without_evidence": found.dropped, "notes": found.notes}


def resume_project_claims(sv, subject: Subject, job: Job) -> Mapping[str, Any]:
    """Project on a resume: its bullets, then the README of its repository."""
    with sv.pool.connection() as conn:
        row = conn.execute("SELECT name, bullets, repo_url FROM candidate_projects WHERE id = %s::uuid",
                           (subject.id,)).fetchone()
    if row is None:
        raise LookupError(f"resume project {subject.id} does not exist")
    name, bullets, repo_url = row
    earlier = _reused(sv, subject, job, ("resume", "readme"))
    if earlier:
        return earlier

    readme, readme_note = None, "no repository link"
    if repo_url:
        page = sv.tinyfish.fetch([repo_url])[0]
        if page.ok:
            readme, readme_note = page.text, "read"
        else:
            readme_note = f"the repository did not load ({page.error_code or 'no answer'})"
    out = claims_from_resume(sv.model, name, list(bullets or []), readme, job_id=job.id)
    for finding in out.findings:
        if finding.level in ("strong", "review"):
            add_flag(sv.pool, "candidate_project", subject.id, "hidden_ai_instructions", finding.level,
                     "Text aimed at an AI checker was found in the resume bullets or README", finding.as_flag_evidence())
    kept = save_claims(sv.pool, subject, out.claims)
    return {"claims": len(kept), "testable": sum(1 for c in kept if c.testable), "readme": readme_note, "reused": False}


SOURCES: dict[str, Callable[[Any, Subject, Job], Mapping[str, Any]]] = {
    "project": project_claims,
    "candidate_project": resume_project_claims,
}


@stage("claims")
def claims(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    subject = subject_of(job)   # a project or a resume project; anything else is a wiring mistake and raises
    return SOURCES[subject.kind](get_services(ctx.pool), subject, job)
