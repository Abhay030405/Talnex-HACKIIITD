"""Job `custom_test` (Ask TalNex): run one test the user described in their own words on a project's live site.

Added by the Go API with no pipeline (input {"instruction": ...}), for a resume project or a hackathon project. The
instruction becomes a one-off claim, is planned and run like any live test (safety rules, way in, live view and live
screen, a screenshot per step), and the result is this job's result only: nothing is written to claims, results or
scores, so a one-off test can never change a score. Repository-only (VM) custom tests are not supported yet.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim
from talnex_ai.live import Emitter
from talnex_ai.login.ladder import build_way_in
from talnex_ai.safety.site_rules import RunLimits
from talnex_ai.testing.planner.planner import plan_claim
from talnex_ai.testing.runner.runner import run_plan
from talnex_ai.worker.handlers.live_test import choose_plan
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, subject_of


@stage("custom_test")
def custom_test(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    instruction = " ".join(str((job.input or {}).get("instruction") or "").split())[:400]
    if len(instruction) < 3:
        return {"verdict": "could_not_test", "observed": "No test was described.", "steps": []}
    info = load_subject_info(ctx.pool, subject_of(job))
    if not info.live_url:
        return {"verdict": "could_not_test", "steps": [],
                "observed": "Could not test: this project has no live site. Custom tests on the repository (VM) are not supported yet."}

    sv = get_services(ctx.pool)
    cfg = sv.cfg
    events = Emitter(ctx.pool, info.kind, info.id, job_id=job.id, stage="custom_test")
    claim = Claim(text=instruction, claim_group="Core", importance=2, source="criteria")
    way_in = build_way_in(info.live_host, cfg.email, cfg.phone.number)
    plans = plan_claim(sv.model, claim, site_url=info.live_url, way_in=way_in.instructions, job_id=job.id)
    plan = choose_plan(plans)
    if plan is None:
        return {"verdict": "could_not_test", "observed": "No test could be planned from that description.", "steps": []}
    ctx.check()
    events.emit("claim.started", text=instruction, group="Custom test", importance=2, test_type=plan.test_type,
                steps=[s.action for s in plan.steps])
    record = run_plan(
        pool=ctx.pool, store_files=sv.files, tinyfish=getattr(sv, "browser", None) or sv.tinyfish, client=sv.model,
        claim=claim, plan=plan, site_url=info.live_url, subject_id=info.id,
        limits=RunLimits(cfg.limits.max_tries_per_claim, cfg.limits.max_agent_runs_per_project), runner_cfg=cfg.runner,
        uploads_root=sv.uploads_root, way_in=way_in.instructions,
        mailbox=sv.mailbox_for(info.live_host) if way_in.email_enabled else None,
        job_id=job.id, connect=sv.connect, on_event=events, record_as=job.id)
    verdict = {"works": "works", "partly_works": "partly_works", "broken": "broken"}.get(record.outcome, "could_not_test")
    events.emit("verdict", verdict=verdict, confidence="low", reason=record.observed)
    return {"verdict": verdict, "observed": record.observed, "expected": plan.expected_result,
            "steps": [{"action": s.action, "observed": s.observed, "proof_key": s.proof_key} for s in record.steps]}
