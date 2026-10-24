"""Stage `route_discovery` (R4 of the sandbox track, architecture 28.6): find every route of the running backend and link
routes to the project's claims.

Needs the app that `sandbox_run` left running. Works for a hackathon project and a project on a resume alike. Claims that
a route serves are marked as sandbox-tested (or both, when the project also has a live link); routes that serve no claim
become minor claims. The routes and links are saved with the sandbox run for the test stages after this one.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.claims.store import load_claims, save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.route_discovery import discover, to_json
from talnex_ai.sandbox.stack_detect.gather import read_facts
from talnex_ai.sandbox.store import latest_run, update_run
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, subject_of


def _set_track(pool, claim_ids: list[str], track: str) -> None:
    if not claim_ids:
        return
    with pool.connection() as conn:
        conn.execute("UPDATE claims SET track = %s WHERE id = ANY(%s::uuid[])", (track, claim_ids))


@stage("route_discovery")
@never_stall
def route_discovery(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    run = latest_run(ctx.pool, subject)
    if run is None or run.status != "running" or not run.vm_id or not run.port:
        why = (run.status_detail if run and run.status_detail else "the sandbox run did not start")
        return {"skipped": True, "reason": f"the app is not running, so there are no routes to discover ({why})"}

    vm = sv.sandbox.attach(run.vm_id)
    try:
        facts = read_facts(vm)
    except SandboxError as exc:
        update_run(ctx.pool, run.id, status="could_not_run", status_detail=f"the VM ended before route discovery: {exc}"[:500], ended=True)
        return {"skipped": True, "reason": "the VM ended before routes could be discovered"}

    claims = load_claims(ctx.pool, subject, testable_only=True)
    app_dir = (run.resources.get("app_dir") or "")
    found = discover(vm, sv.model, port=run.port, app_dir=app_dir, facts=facts, claims=claims, job_id=job.id)

    # Claims served by a route are tested by the sandbox; with a live link too, both tracks test them and must agree.
    serves = list(found.links)
    _set_track(ctx.pool, serves, "both" if info.live_url else "sandbox")

    saved = save_claims(ctx.pool, subject, found.minor_claims) if found.minor_claims else []
    links = dict(found.links)
    for claim, route_index in zip(saved, found.minor_routes):
        if claim.id:
            links[claim.id] = [route_index]
    found.links = links

    update_run(ctx.pool, run.id, resources={"discovery": to_json(found)})
    return {
        "routes": len(found.routes), "spec_found": found.spec_found, "claims_linked": len(serves),
        "minor_claims": len(saved), "notes": found.notes,
        "sources": sorted({r.source for r in found.routes}),
    }
