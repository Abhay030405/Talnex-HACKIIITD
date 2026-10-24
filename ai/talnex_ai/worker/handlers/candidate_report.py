"""Stage `candidate_report` (recruiter_report pipeline, one per candidate): builds the proof report and saves it.

One report per candidate; running again replaces it, so the job is safe to run twice. `resume_cleanup` (Go) runs after it.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.reports.recruiter_report import build_report
from talnex_ai.worker.registry import JobContext, stage


@stage("candidate_report")
def candidate_report(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    report = build_report(ctx.pool, job.target_id)
    ctx.check()
    with ctx.pool.connection() as conn:
        conn.execute(
            """INSERT INTO candidate_reports (candidate_id, report, has_gaps, generated_at)
               VALUES (%s::uuid, %s::jsonb, %s, now())
               ON CONFLICT (candidate_id) DO UPDATE SET
                   report = EXCLUDED.report, has_gaps = EXCLUDED.has_gaps, generated_at = EXCLUDED.generated_at""",
            (job.target_id, json.dumps(report, default=str), report["has_gaps"]))
    return {"projects": len(report["projects"]), "has_gaps": report["has_gaps"],
            "saved_minutes": report["time_saved"]["saved_minutes"]}
