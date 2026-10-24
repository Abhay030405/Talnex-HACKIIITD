"""Stage `repo_tests` (R7 of the sandbox track, architecture 28.7): run the repository's own test command inside the VM and
save how many tests passed, as evidence for the Reliability group (a claim of importance 1).

Works for a hackathon project and a project on a resume alike, and needs the VM `sandbox_run` left running. The verdict is
never "broken": a repo's tests can need a database or a key the sandbox does not have, so tests that all fail here are
"could not confirm". The full output is saved as proof.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from talnex_ai.claims.store import save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim, Result, StepRecord
from talnex_ai.safety.site_rules import tries_used_for_claim
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.repo_tests import describe, parse_test_output
from talnex_ai.sandbox.stack_detect.gather import REPO_DIR
from talnex_ai.sandbox.store import latest_run
from talnex_ai.scoring.store import save_result
from talnex_ai.storage.keys import sandbox_key
from talnex_ai.testing.runner import store
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import subject_of

log = logging.getLogger("talnex.repo_tests")

CLAIM_TEXT = "The repository's own tests pass"
_DB_OUTCOME = {"works": "passed", "partly_works": "passed", "could_not_test": "blocked"}


def with_runner_installed(test_cmd: str) -> str:
    """pytest is not always in a repo's dependency list, so make sure it is there before it is used."""
    return f"python -m pip install -q pytest >/dev/null 2>&1; {test_cmd}" if "pytest" in test_cmd else test_cmd


@stage("repo_tests")
@never_stall
def repo_tests(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    run = latest_run(ctx.pool, subject)
    if run is None or run.status != "running" or not run.vm_id:
        return {"skipped": True, "reason": "the app is not running, so the repository's tests were not run"}
    recipe = run.recipe or {}
    command = (recipe.get("test_cmd") or "").strip()
    if not command:
        return {"skipped": True, "reason": "the repository has no test command we could find"}

    (claim,) = save_claims(ctx.pool, subject, [Claim(text=CLAIM_TEXT, claim_group="Reliability", importance=1, source="readme", track="sandbox")])
    vm = sv.sandbox.attach(run.vm_id)
    app_dir = run.resources.get("app_dir") or ""
    workdir = f"{REPO_DIR}/{app_dir}" if app_dir else REPO_DIR
    try:
        res = vm.exec(with_runner_installed(command), workdir=workdir, env=recipe.get("env") or {}, timeout_seconds=sv.cfg.sandbox.build_timeout_seconds)
    except SandboxError as exc:
        save_result(ctx.pool, Result(claim_id=claim.id or "", verdict="could_not_test", confidence="low", reason=f"not tested: the sandbox failed ({exc})"))
        return {"skipped": True, "reason": f"the sandbox failed: {exc}"}

    counts = parse_test_output(res.output)
    verdict, reason = describe(counts, res.exit_code, res.timed_out)

    run_id = store.create_run(ctx.pool, claim.id or "", tries_used_for_claim(ctx.pool, claim.id or "") + 1, "repo_tests", track="sandbox", method="command")
    key = sandbox_key(subject.id, run_id, "tests.log")
    try:
        sv.files.put_bytes(key, res.output.encode("utf-8", errors="replace"), "text/plain; charset=utf-8")
    except Exception as exc:  # the verdict stands without its file
        log.warning("could not save the test log %s: %s", key, exc)
        key = None  # type: ignore[assignment]
    store.add_steps(ctx.pool, run_id, [StepRecord(
        step_number=1, kind="command", action=command[:300], expected="the repository's own tests pass",
        observed=reason[:500], proof_key=key, duration_ms=res.duration_ms)])
    store.finish_run(ctx.pool, run_id, _DB_OUTCOME[verdict])
    save_result(ctx.pool, Result(claim_id=claim.id or "", verdict=verdict, confidence="medium" if verdict != "could_not_test" else "low",  # type: ignore[arg-type]
                                 reason=reason, proof_keys=[key] if key else []))
    return {"verdict": verdict, "reason": reason, "passed": counts.passed if counts else None, "failed": counts.failed if counts else None,
            "framework": counts.framework if counts else None}

