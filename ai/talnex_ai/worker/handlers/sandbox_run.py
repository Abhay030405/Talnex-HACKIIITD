"""Stage `sandbox_run` (R2 and R3 of the sandbox track, architecture section 28): clone the repo into a throwaway VM,
work out how to run it, build it and start it.

Works for a hackathon project and a project on a resume alike. When the app comes up, the VM stays alive and its id and
port are saved in `sandbox_runs`, so the stages after this one find the running app. When it cannot run, the VM is
destroyed and the reason is saved: "could not run" is never "broken", and it is left out of every score.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.stack_detect import prepare_and_run
from talnex_ai.sandbox.store import create_run, latest_run, update_run
from talnex_ai.storage.keys import sandbox_key
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, subject_of

log = logging.getLogger("talnex.sandbox_run")


def _save_log(sv, subject_id: str, run_id: str, name: str, text: str) -> str:
    key = sandbox_key(subject_id, run_id, name)
    sv.files.put_bytes(key, text.encode("utf-8", errors="replace"), "text/plain; charset=utf-8")
    return key


def _could_not_run(ctx: JobContext, run_id: str, reason: str, **fields: Any) -> Mapping[str, Any]:
    update_run(ctx.pool, run_id, status="could_not_run", status_detail=reason[:500], ended=True, **fields)
    return {"status": "could_not_run", "reason": reason, "run_id": run_id}


@stage("sandbox_run")
@never_stall
def sandbox_run(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    if not info.repo_url:
        return {"skipped": True, "reason": "no repository link was given"}

    # A run that was left behind by an earlier try of this stage must not keep its VM alive.
    previous = latest_run(ctx.pool, subject)
    if previous is not None and previous.vm_id and previous.status == "running" and sv.sandbox is not None:
        try:
            sv.sandbox.destroy(previous.vm_id)
        except SandboxError:
            pass
        update_run(ctx.pool, previous.id, status="done", status_detail="replaced by a newer run", ended=True)

    run_id = create_run(ctx.pool, subject)
    if sv.sandbox is None or not sv.cfg.sandbox.enabled:
        return _could_not_run(ctx, run_id, "the sandbox host is not set up")

    update_run(ctx.pool, run_id, status="building")
    try:
        result = prepare_and_run(
            lambda image, services=(): sv.sandbox.open_vm(image, services=list(services)),
            sv.model, info.repo_url,
            build_timeout_seconds=sv.cfg.sandbox.build_timeout_seconds, job_id=job.id,
        )
    except SandboxError as exc:  # the host is down or full: not the project's fault, and a retry may work
        update_run(ctx.pool, run_id, status="could_not_run", status_detail=f"the sandbox host failed: {exc}"[:500], ended=True)
        raise

    recipe = result.recipe.model_dump() if result.recipe else {}
    fields: dict[str, Any] = {"recipe": recipe, "image": result.recipe.image if result.recipe else None}
    if result.attempts:
        fields["build_log_key"] = _save_log(sv, subject.id, run_id, "build.log", result.build_log())
        last = result.attempts[-1]
        if last.app_log_tail:
            fields["run_log_key"] = _save_log(sv, subject.id, run_id, "run.log", last.app_log_tail)

    if not result.ok:
        return _could_not_run(ctx, run_id, result.reason, **fields)

    bring = result.bringup
    detail = "the app is running" if bring.ok else "the app is running, but its health paths answer with a server error"
    update_run(ctx.pool, run_id, status="running", status_detail=detail,
               resources={"vm_id": result.vm.id, "port": bring.port, "health_path": bring.health_path,
                          "app_dir": result.recipe.app_dir, "repo_dir": "/work/repo"},
               **fields)
    return {
        "status": "running", "run_id": run_id, "stack": result.recipe.stack, "port": bring.port,
        "health_path": bring.health_path, "recipe_source": result.recipe.source, "fix_used": result.fix_used,
        "services_seen": result.recipe.services,
    }
