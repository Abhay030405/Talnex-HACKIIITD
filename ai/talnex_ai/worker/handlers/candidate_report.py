"""Stage `candidate_report` (recruiter_report pipeline, one per candidate): builds the proof report and saves it.

One report per candidate; running again replaces it, so the job is safe to run twice. `resume_cleanup` (Go) runs after it.
It starts when the last resume project finishes, but the coding checks (`recruiter_coding`) run beside the projects, so it
first waits for those of the same run; if they are still going at the limit, the report is built anyway with a note.
"""
from __future__ import annotations

import json
import time
from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.reports.recruiter_report import build_report
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services

POLL_SECONDS = 10


def coding_still_running(pool, candidate_id: str, run_number: int) -> int:
    with pool.connection() as conn:
        return conn.execute(
            """SELECT count(*) FROM jobs WHERE pipeline = 'recruiter_coding' AND target_type = 'candidate'
                AND target_id = %s::uuid AND run_number = %s AND status IN ('queued', 'running', 'retrying')""",
            (candidate_id, run_number)).fetchone()[0]


def wait_for_coding(job: Job, ctx: JobContext, wait_seconds: int, sleep=time.sleep) -> int:
    """Wait (within the job's time limit) until the coding checks of this run are done. Returns how many still run."""
    end = time.monotonic() + min(wait_seconds, max(0.0, ctx.remaining() - 60))   # keep a minute to build the report
    left = coding_still_running(ctx.pool, job.target_id, job.run_number)
    while left and time.monotonic() < end:
        sleep(POLL_SECONDS)
        ctx.check()
        left = coding_still_running(ctx.pool, job.target_id, job.run_number)
    return left


@stage("candidate_report")
def candidate_report(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    cfg = get_services(ctx.pool).cfg
    still_running = wait_for_coding(job, ctx, getattr(cfg, "report_coding_wait_seconds", 480) if cfg else 0)
    report = build_report(ctx.pool, job.target_id)
    if still_running:
        report["notes"].append("Some coding profile checks were still running when this report was made; their "
                               "results are not included.")
    ctx.check()
    with ctx.pool.connection() as conn:
        conn.execute(
            """INSERT INTO candidate_reports (candidate_id, report, has_gaps, generated_at)
               VALUES (%s::uuid, %s::jsonb, %s, now())
               ON CONFLICT (candidate_id) DO UPDATE SET
                   report = EXCLUDED.report, has_gaps = EXCLUDED.has_gaps, generated_at = EXCLUDED.generated_at""",
            (job.target_id, json.dumps(report, default=str), report["has_gaps"]))
    return {"projects": len(report["projects"]), "has_gaps": report["has_gaps"], "coding_checks_missing": still_running,
            "saved_minutes": report["time_saved"]["saved_minutes"]}
