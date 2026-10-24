"""Stage `sandbox_end`: destroy the VM that held the running app and close the sandbox run (architecture 28.2: the VM is
destroyed before the code review). Works for a hackathon project and a project on a resume alike, and is safe to run twice."""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.store import latest_run, update_run
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import subject_of


@stage("sandbox_end")
@never_stall
def sandbox_end(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    run = latest_run(ctx.pool, subject_of(job))
    if run is None or not run.vm_id or run.status != "running":
        return {"skipped": True, "reason": "there was no running VM to end"}
    if sv.sandbox is not None:
        sv.sandbox.attach(run.vm_id).destroy()   # never raises: a VM already gone is fine, the reaper covers the rest
    update_run(ctx.pool, run.id, status="done", status_detail="the tests are finished and the VM was destroyed", ended=True)
    return {"destroyed": run.vm_id}
