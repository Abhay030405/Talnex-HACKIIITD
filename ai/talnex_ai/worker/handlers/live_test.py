"""Stage `live_test`: use the live site for every testable claim and save a verdict for each, with proof.

Each claim goes through the never-blame ladder (testing/retries): a test run, the independent proof
check, and only if it looks broken, a wait, a second run planned a different way, and a second check.

Works the same for a hackathon project and a project on a resume. Claims are tested a few at a time.
A claim that already has a result from THIS job (a retry after a crash) isn't tested again, so tries
aren't wasted and good results are never overwritten.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from psycopg_pool import ConnectionPool

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim, Result, TestPlan
from talnex_ai.live import Emitter, NullEmitter
from talnex_ai.login.ladder import build_way_in
from talnex_ai.safety.hidden_instructions.rendered import orders_in_hidden_text
from talnex_ai.safety.site_rules import LimitReached, RunLimits
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.scoring.store import save_result
from talnex_ai.testing.planner.planner import plan_claim
from talnex_ai.testing.proof_check import check_proof, devtools_notes, screens_for_check
from talnex_ai.testing.retries import LadderDeps, judge_claim, to_result
from talnex_ai.testing.runner.runner import run_plan
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import SubjectInfo, job_started_at, load_subject_info, set_status, stage_result, subject_of

log = logging.getLogger("talnex.live_test")

MIN_SECONDS_TO_START_A_CLAIM = 150  # don't start a new claim with less of the stage's time left than this
# Which extra check runs first when several are planned: bad input shows how mistakes are handled, a
# known answer whether the output is right, a repeat whether it's steady.
EXTRA_ORDER = ("bad_input", "known_answer", "repeat")


def could_not_test(claim_id: str, reason: str) -> Result:
    return Result(claim_id=claim_id, verdict="could_not_test", confidence="low", reason=reason)


def has_result_since(pool: ConnectionPool, claim_id: str, since: datetime) -> bool:
    with pool.connection() as conn:
        row = conn.execute("SELECT created_at, verdict FROM results WHERE claim_id = %s::uuid", (claim_id,)).fetchone()
    # A "reviewed from code" result doesn't count: reading the code isn't testing the live site.
    return bool(row and row[0] >= since and row[1] != "reviewed_from_code")


def choose_plan(plans: Sequence[TestPlan]) -> Optional[TestPlan]:
    """The plan that goes through the full ladder: the normal test, or the access test for sign-in claims."""
    for wanted in ("normal", "access"):
        for plan in plans:
            if plan.test_type == wanted:
                return plan
    return plans[0] if plans else None


def extra_plans(plans: Sequence[TestPlan], how_many: int) -> list[TestPlan]:
    """The planned checks beyond the main test, in EXTRA_ORDER, at most `how_many`."""
    chosen = [p for wanted in EXTRA_ORDER for p in [q for q in plans if q.test_type == wanted][:1]]
    return chosen[:max(0, how_many)]


def judge_one(sv: Any, info: SubjectInfo, claim: Claim, saved: Mapping[str, Any], job_id: Optional[str],
              events: Any = None) -> str:
    """Test one claim and save its result. Returns the verdict. Never raises: our problems are "could not test".

    `sv` is the shared services object (worker/services.py): pool, cfg, model, tinyfish, files, connect,
    uploads_root, mailbox_for and smsbox_for. `events` streams progress to the live view."""
    ev = (events or NullEmitter()).child(claim_id=claim.id)

    def finish(result: Result) -> str:
        save_result(sv.pool, result)
        ev.emit("verdict", verdict=result.verdict, confidence=result.confidence, reason=result.reason,
                proof_keys=result.proof_keys[:4], second_check_agreed=result.second_check_agreed)
        return result.verdict

    try:
        if "error" in saved:
            return finish(could_not_test(claim.id, f"no test could be written for this claim ({saved['error']})"))
        all_plans = [TestPlan.model_validate(p) for p in saved.get("plans", [])]
        plan = choose_plan(all_plans)
        if plan is None:
            return finish(could_not_test(claim.id, "no test was planned for this claim"))
        ev.emit("claim.started", text=claim.text, group=claim.claim_group, importance=claim.importance,
                test_type=plan.test_type, steps=[s.action for s in plan.steps])

        cfg = sv.cfg
        way_in = build_way_in(info.live_host, cfg.email, cfg.phone.number)
        mailbox = sv.mailbox_for(info.live_host) if way_in.email_enabled else None
        smsbox = sv.smsbox_for(info.live_host) if way_in.phone_enabled and getattr(sv, "smsbox_for", None) else None
        limits = RunLimits(cfg.limits.max_tries_per_claim, cfg.limits.max_agent_runs_per_project)

        def on_hidden_text(pieces: list[str]) -> None:
            for finding in orders_in_hidden_text(pieces):
                add_flag(sv.pool, info.kind, info.id, "hidden_ai_instructions", "strong",
                         "Hidden text aimed at an AI checker was found on the live site", finding.as_flag_evidence())

        def run(p: TestPlan):
            return run_plan(pool=sv.pool, store_files=sv.files, tinyfish=getattr(sv, "browser", None) or sv.tinyfish,
                            client=sv.model, claim=claim,
                            plan=p, site_url=info.live_url, subject_id=info.id, limits=limits, runner_cfg=cfg.runner,
                            uploads_root=sv.uploads_root, way_in=way_in.instructions, mailbox=mailbox, smsbox=smsbox,
                            job_id=job_id, connect=sv.connect, on_hidden_text=on_hidden_text, on_event=ev)

        def alternate(p: TestPlan, _previous) -> TestPlan:
            fresh = plan_claim(sv.model, claim, site_url=info.live_url, avoid=p, only=p.test_type, job_id=job_id)
            if not fresh:
                raise ValueError("no second plan")
            return fresh[0]

        def check(record, p: TestPlan):
            screens = screens_for_check(record.steps)
            notes = devtools_notes(record.steps)
            ev.emit("check.started", images=len(screens))
            found = check_proof(sv.model, sv.files, claim_text=claim.text, expected_result=p.expected_result,
                                proof_keys=screens, notes=notes, job_id=job_id, checks=p.checks)
            ev.emit("check", outcome=found.outcome, seen=found.seen, images=found.images_used, parts=list(found.parts))
            return found

        deps = LadderDeps(fetch=lambda url: sv.tinyfish.fetch([url])[0], run=run, alternate=alternate, check=check,
                          wait_seconds=cfg.limits.sleeping_host_wait_seconds,
                          on_trace=lambda line: ev.emit("ladder", line=line))
        result = to_result(claim.id, judge_claim(plan, info.live_url, deps))
        finish(result)
        if result.verdict in ("works", "partly_works"):
            # The main test passed, so extra checks are only evidence for the score: they never change the verdict.
            for extra in extra_plans(all_plans, cfg.limits.extra_tests_per_claim):
                try:
                    run(extra)
                except LimitReached as err:
                    log.info("no extra check for claim %s: %s", claim.id, err)
                    break
                except Exception as err:  # an extra check that can't run just leaves its checklist items unchecked
                    log.warning("extra check %s for claim %s failed: %s", extra.test_type, claim.id, err)
        return result.verdict
    except Exception as err:  # a problem on our side is never the project's fault
        log.exception("testing claim %s hit a problem", claim.id)
        return finish(could_not_test(claim.id, f"the test hit a problem on our side ({type(err).__name__})"))


def live_test_subject(sv: Any, info: SubjectInfo, claims: Sequence[Claim], precheck: Mapping[str, Any],
                 plans: Mapping[str, Any], since: datetime, job_id: Optional[str],
                 seconds_left=lambda: float("inf"), events: Any = None) -> dict[str, Any]:
    """Test every claim of one subject, a few at a time, streaming progress to the live view."""
    if events is None:
        events = Emitter(sv.pool, info.kind, info.id, job_id=job_id, stage="live_test")

    def skip(claim: Claim, why: str) -> str:
        save_result(sv.pool, could_not_test(claim.id, why))
        events.child(claim_id=claim.id).emit("verdict", verdict="could_not_test", confidence="low", reason=why)
        return "could_not_test"

    reason: Optional[str] = None
    if not info.live_url:
        reason = "no live link was given"
    elif precheck.get("live") and not precheck["live"].get("ok"):
        reason = f"the live link did not load ({precheck['live'].get('error_code') or 'no answer'})"
    elif plans.get("skipped"):
        reason = plans.get("reason") or "no test plans"
    if reason:
        for claim in claims:
            if not has_result_since(sv.pool, claim.id, since):
                skip(claim, f"not tested: {reason}")
        return {"skipped": True, "reason": reason}

    claim_plans = plans.get("claims", {})
    todo = [c for c in claims if not has_result_since(sv.pool, c.id, since)]

    events.emit("claims.queued", total=len(claims), todo=len(todo), claims=[{"id": c.id, "text": c.text} for c in todo])

    def work(claim: Claim) -> str:
        if seconds_left() < MIN_SECONDS_TO_START_A_CLAIM:
            return skip(claim, "not tested: the stage ran out of time")
        return judge_one(sv, info, claim, claim_plans.get(claim.id, {"error": "no plan was saved"}), job_id, events)

    with ThreadPoolExecutor(max_workers=max(1, min(sv.cfg.tinyfish.parallel_runs, len(todo) or 1))) as threads:
        verdicts = list(threads.map(work, todo))
    counts: dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict] = counts.get(verdict, 0) + 1
    return {"tested": len(verdicts), "already_done": len(claims) - len(todo), "verdicts": counts}


@stage("live_test")
def live_test(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    # Claims only the repository can test (a backend route, setup, edge cases) belong to the sandbox track.
    claims = [c for c in load_claims(ctx.pool, subject, testable_only=True) if c.track != "sandbox"]
    if not claims:
        return {"skipped": True, "reason": "there are no testable claims for the live site"}
    set_status(ctx.pool, info, "testing")
    return live_test_subject(get_services(ctx.pool), info, claims, stage_result(ctx.pool, job, "precheck") or {},
                        stage_result(ctx.pool, job, "test_plan") or {}, job_started_at(ctx.pool, job), job.id,
                        seconds_left=ctx.remaining)
