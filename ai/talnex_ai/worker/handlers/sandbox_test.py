"""Stage `sandbox_test` (R6 and R8 of the sandbox track, architecture 28.7 and 28.10): run the backend tests and save a
verdict for every claim, with proof.

Each claim goes through the same never-blame ladder as a live claim (testing/retries): a try, an independent check of the
saved requests and answers, and, only if it looks broken, a second try built a different way and a second independent check.
Only then can the word "broken" be used. The app answering with an error to a bad request is a result; the app not
answering, a sign-in we do not have, or a route we may have found wrongly are "could not confirm", never a mark against the team.

Works for a hackathon project and a project on a resume alike. The Setup claim is judged from how the run came up.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim, Result
from talnex_ai.safety.site_rules import LimitReached
from talnex_ai.sandbox.api_tests.derive import AUTH_TEXT, SETUP_TEXT, session_header_from
from talnex_ai.sandbox.api_tests.executor import run_http_plan
from talnex_ai.sandbox.api_tests.plan import HttpPlan
from talnex_ai.sandbox.api_tests.planner import plan_claim_http
from talnex_ai.sandbox.api_tests.proof import check_http_proof
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.route_discovery import from_json
from talnex_ai.sandbox.store import SandboxRun, latest_run
from talnex_ai.scoring.store import save_result
from talnex_ai.testing.retries import LadderDeps, judge_claim, to_result
from talnex_ai.tinyfish.client import FetchResult
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import Services, get_services
from talnex_ai.worker.subjects import SubjectInfo, load_subject_info, stage_result, subject_of

log = logging.getLogger("talnex.sandbox_test")

# A sleeping host is a reason to wait on a live site; a repo in our own VM is not asleep, so the wait before a second try is short.
WAIT_BEFORE_SECOND_TRY = 3
MAX_CLAIMS = 60


def _could_not_test(claim_id: str, reason: str) -> Result:
    return Result(claim_id=claim_id, verdict="could_not_test", confidence="low", reason=reason)


def setup_result(claim_id: str, run: SandboxRun) -> Result:
    """The Setup claim, judged from how the app came up. A setup that needed a fix is partly working: the instructions were incomplete."""
    recipe = run.recipe or {}
    proof = [k for k in (run.build_log_key, run.run_log_key) if k]
    if recipe.get("source") == "model_fix":
        note = next((n for n in recipe.get("notes", []) if str(n).startswith("model fix:")), "")
        return Result(claim_id=claim_id, verdict="partly_works", confidence="medium", proof_keys=proof,
                      reason="the app runs, but the steps in the repository were not enough: an automatic fix was needed. " + note[:300])
    how = {"dockerfile": "from its Dockerfile", "readme": "from the steps in its README", "package_files": "from its package files"}.get(
        recipe.get("source", ""), "from its files")
    return Result(claim_id=claim_id, verdict="works", confidence="high", proof_keys=proof,
                  reason=f"it installed and started {how} and answered on port {run.port}")


def _alternate_deterministic(plan: HttpPlan) -> HttpPlan:
    """The same checks built another way: each path with its trailing slash added or removed (apps often treat the two differently)."""
    def flip(path: str) -> str:
        return path.rstrip("/") if path.endswith("/") and path != "/" else (path if path == "/" else path + "/")

    return plan.model_copy(update={"steps": [s.model_copy(update={"path": flip(s.path)}) for s in plan.steps]})


def _judge(sv: Services, info: SubjectInfo, run: SandboxRun, vm, claim: Claim, plans: list[HttpPlan], routes, job: Job,
           auth: dict[str, str]) -> Result:
    cfg = sv.cfg
    health = run.resources.get("health_path") or "/"
    port = int(run.port or 0)
    main = next((p for p in plans if p.test_type == claim_main_type(claim, plans)), plans[0])
    modelled = main.test_type in ("normal", "known_answer", "repeat")

    def alive(_url: str) -> FetchResult:
        res = vm.request("GET", port, health, timeout_seconds=10)
        return FetchResult(url=health, ok=res.answered and res.status < 500, error_code=res.error or f"status {res.status}")

    is_sign_in = claim.text == AUTH_TEXT

    def run_one(p: HttpPlan):
        captured: dict[str, str] = {}
        cookies: dict[str, str] = {}
        record = run_http_plan(pool=sv.pool, files=sv.files, vm=vm, port=port, claim=claim, plan=p, subject_id=info.id,
                               max_tries_per_claim=cfg.limits.max_tries_per_claim, default_headers=dict(auth) or None,
                               variables_out=captured, cookies_out=cookies)
        if is_sign_in and record.outcome in ("works", "partly_works"):
            # every later test now sends this token or session cookie (access tests go without on purpose)
            auth.update(session_header_from(p, captured, cookies))
        return record

    def alternate(p: HttpPlan, _previous) -> HttpPlan:
        if not modelled:
            return _alternate_deterministic(p)
        fresh = plan_claim_http(sv.model, claim, routes, avoid=p, only=p.test_type, job_id=job.id)
        if not fresh:
            raise ValueError("no second plan")
        return fresh[0]

    def check(record, p: HttpPlan):
        return check_http_proof(sv.model, sv.files, claim_text=claim.text, expected_result=p.expected_result,
                                proof_keys=[s.proof_key for s in record.steps], job_id=job.id)

    deps = LadderDeps(fetch=alive, run=run_one, alternate=alternate, check=check, wait_seconds=WAIT_BEFORE_SECOND_TRY)
    ladder = judge_claim(main, health, deps)  # type: ignore[arg-type]
    result = to_result(claim.id or "", ladder)
    if result.verdict in ("works", "partly_works"):
        # The main test passed, so the extra checks are only evidence for the score; they never change the verdict.
        for extra in [p for p in plans if p is not main][: max(0, cfg.limits.extra_tests_per_claim)]:
            try:
                run_one(extra)
            except LimitReached:
                break
            except Exception as exc:  # an extra check that cannot run just leaves those items unchecked
                log.warning("extra check %s for claim %s failed: %s", extra.test_type, claim.id, exc)
    return result


def claim_main_type(claim: Claim, plans: list[HttpPlan]) -> str:
    """The plan that decides the verdict: the claim's own kind of test, else the normal one."""
    types = [p.test_type for p in plans]
    for wanted in ("edge_case", "access", "light_load", "route_smoke", "normal"):
        if wanted in types:
            return wanted
    return types[0]


@stage("sandbox_test")
@never_stall
def sandbox_test(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    run = latest_run(ctx.pool, subject)
    if run is None or run.status != "running" or not run.vm_id or not run.port:
        return {"skipped": True, "reason": "the app is not running, so there is nothing to test"}
    planned = (stage_result(ctx.pool, job, "sandbox_plan") or {})
    if planned.get("skipped") or not planned.get("claims"):
        return {"skipped": True, "reason": planned.get("reason") or "no backend tests were planned"}

    vm = sv.sandbox.attach(run.vm_id)
    routes = from_json(run.resources.get("discovery") or {}).routes
    claims = {c.id: c for c in load_claims(ctx.pool, subject, testable_only=True) if c.id}
    counts: dict[str, int] = {}
    auth: dict[str, str] = {}   # the sign-in header once the sign-in test has run

    def record(verdict: str) -> None:
        counts[verdict] = counts.get(verdict, 0) + 1

    # The Setup claim has no requests to send: it is judged from how the app came up.
    for claim in claims.values():
        if claim.text == SETUP_TEXT:
            save_result(sv.pool, setup_result(claim.id or "", run))
            record("works" if run.recipe.get("source") != "model_fix" else "partly_works")

    # The sign-in claim goes first, so the others can use its token.
    ordered = sorted(planned["claims"].items(), key=lambda kv: 0 if (claims.get(kv[0]) and claims[kv[0]].text == AUTH_TEXT) else 1)
    for claim_id, entry in ordered[:MAX_CLAIMS]:
        claim = claims.get(claim_id)
        if claim is None:
            continue
        if ctx.remaining() < 60:
            save_result(sv.pool, _could_not_test(claim_id, "not tested: the stage ran out of time"))
            record("could_not_test")
            continue
        try:
            plans = [HttpPlan.model_validate(p) for p in entry.get("plans", [])]
            result = _judge(sv, info, run, vm, claim, plans, routes, job, auth) if plans else _could_not_test(claim_id, "no test was planned for this claim")
        except SandboxError as exc:
            # The VM or the host failed: not the project's fault, and the verdict is left untested.
            result = _could_not_test(claim_id, f"not tested: the sandbox failed ({exc})")
        except Exception as exc:  # a problem on our side is never the project's fault
            log.exception("testing claim %s hit a problem", claim_id)
            result = _could_not_test(claim_id, f"the test hit a problem on our side ({type(exc).__name__})")
        save_result(sv.pool, result)
        record(result.verdict)

    for claim_id, reason in (planned.get("errors") or {}).items():
        if claim_id in claims and claim_id not in planned["claims"]:
            save_result(sv.pool, _could_not_test(claim_id, f"not tested: {reason}"))
            record("could_not_test")
    return {"tested": sum(counts.values()), "verdicts": counts}
