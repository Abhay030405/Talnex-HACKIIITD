"""Stage `code_review` (R9 of the sandbox track, architecture 28.8 and 29.2): read the cloned code for each claim and judge
whether the claimed feature is really written, and how well.

Works for a hackathon project and a project on a resume alike. It reads the code inside the VM `sandbox_run` left running, so
it needs no network. The finding (mechanism present, partial, missing or unclear, with file and line references and notes on
how it is written) is kept with the run and shown to the score stage as evidence, labelled "reviewed from code, not run".

  - A claim nothing else could test (no live link, not reachable through a route) gets the verdict "reviewed from code", which
    the score caps at 7/10. A mechanism that is plainly missing from the code scores 0 (the checklist marks it missing).
  - A claim that was really tested keeps its tested verdict; the review is extra evidence for its score.
  - "Unclear" (we could not find the code, or did not read enough) never lowers anything.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Result
from talnex_ai.sandbox.api_tests.derive import SETUP_TEXT
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.code_review import review_claim
from talnex_ai.sandbox.route_discovery import from_json
from talnex_ai.sandbox.stack_detect.gather import read_facts
from talnex_ai.sandbox.store import latest_run, save_code_review
from talnex_ai.scoring.store import save_result
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import subject_of

log = logging.getLogger("talnex.code_review")

MAX_CLAIMS_REVIEWED = 15
REPO_TESTS_TEXT = "The repository's own tests pass"
TESTED = ("works", "partly_works", "broken")


def worth_reviewing(claim) -> bool:
    """The claims a project makes about itself. Claims TalNex made up from the routes (setup, edge cases, route checks) are not reviewed."""
    return claim.source != "route" and claim.text not in (SETUP_TEXT, REPO_TESTS_TEXT) and claim.claim_group not in ("Setup", "Edge cases")


def _result_for(finding, claim_id: str) -> Result | None:
    label = "reviewed from code, not run"
    if finding.mechanism in ("present", "partial"):
        return Result(claim_id=claim_id, verdict="reviewed_from_code", confidence="medium" if finding.mechanism == "present" else "low",
                      reason=f"{label}: the mechanism is {'there' if finding.mechanism == 'present' else 'only partly there'}. {finding.summary}"[:900])
    if finding.mechanism == "missing":
        return Result(claim_id=claim_id, verdict="reviewed_from_code", confidence="medium",
                      reason=f"{label}: the claimed mechanism was not found in the code. {finding.summary}"[:900])
    return None   # unclear: nothing is said, and nothing is lowered


@stage("code_review")
@never_stall
def code_review(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    run = latest_run(ctx.pool, subject)
    if run is None or run.status != "running" or not run.vm_id:
        return {"skipped": True, "reason": "the code is not available (the app did not run), so no code review was done"}
    vm = sv.sandbox.attach(run.vm_id)
    try:
        facts = read_facts(vm)
    except SandboxError as exc:
        return {"skipped": True, "reason": f"the VM ended before the code could be read ({exc})"}

    claims = [c for c in load_claims(ctx.pool, subject, testable_only=True) if c.id and worth_reviewing(c)]
    claims.sort(key=lambda c: -c.importance)
    app_dir = run.resources.get("app_dir") or ""
    discovery = from_json(run.resources.get("discovery") or {})
    cfg = sv.cfg.sandbox
    counts: dict[str, int] = {}
    for claim in claims[:MAX_CLAIMS_REVIEWED]:
        if ctx.remaining() < 90:
            break
        linked = sorted({discovery.routes[i].file for i in discovery.links.get(claim.id, []) if i < len(discovery.routes) and discovery.routes[i].file})
        try:
            finding, chosen = review_claim(sv.model, vm, claim.text, facts.files, app_dir, linked_files=linked,
                                           max_files=cfg.review_max_files, max_kb=cfg.review_max_kb, job_id=job.id)
        except SandboxError:
            break    # the VM is gone: the rest cannot be read, and nothing is blamed on the project
        except Exception as exc:  # one claim that cannot be reviewed must not stop the others
            log.warning("could not review claim %s: %s", claim.id, exc)
            continue
        record = finding.model_dump()
        record.update({"files_read": chosen.paths, "all_source_shown": chosen.all_source_shown})
        save_code_review(ctx.pool, run.id, claim.id, record)
        counts[finding.mechanism] = counts.get(finding.mechanism, 0) + 1

        result = _result_for(finding, claim.id)
        if result is not None:
            with ctx.pool.connection() as conn:
                existing = conn.execute("SELECT verdict FROM results WHERE claim_id = %s::uuid", (claim.id,)).fetchone()
            if existing is None or existing[0] not in TESTED:
                save_result(ctx.pool, result)
    return {"reviewed": sum(counts.values()), "mechanisms": counts, "of": len(claims)}
