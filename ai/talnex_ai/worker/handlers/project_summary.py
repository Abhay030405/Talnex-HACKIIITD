"""Stage `project_summary` (recruiter, one per resume project): the last stage of a project.

When every project on the resume has reached this stage, the candidate moves to `reporting` and the
`recruiter_report` pipeline starts (build the proof report, then delete the resume). Starting it twice adds nothing.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.db import jobs as queue
from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, stage


def save_partial_report(pool, candidate_id: str) -> None:
    """Results so far, shown while other projects still run. Never replaces a final report; the final one replaces it."""
    import json

    from talnex_ai.reports.recruiter_report import build_report

    report = build_report(pool, candidate_id)
    report["partial"] = True
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO candidate_reports (candidate_id, report, has_gaps, generated_at)
               VALUES (%s::uuid, %s::jsonb, true, now())
               ON CONFLICT (candidate_id) DO UPDATE SET report = EXCLUDED.report, generated_at = now()
               WHERE candidate_reports.report->>'partial' = 'true'""",
            (candidate_id, json.dumps(report, default=str)))


@stage("project_summary")
def project_summary(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    with ctx.pool.connection() as conn:
        candidate_id = conn.execute("SELECT candidate_id::text FROM candidate_projects WHERE id = %s::uuid",
                                    (job.target_id,)).fetchone()[0]
        # A project has "reached" this stage when its summary job is running or done. Counting running ones means
        # two projects finishing at the same moment cannot both think the other is still waiting.
        waiting = conn.execute(
            """SELECT count(*) FROM candidate_projects cp
                WHERE cp.candidate_id = %s::uuid AND cp.id <> %s::uuid
                  AND (EXISTS (SELECT 1 FROM jobs j2 WHERE j2.pipeline = 'recruiter' AND j2.target_type = 'candidate_project'
                                  AND j2.target_id = cp.id AND j2.run_number = %s)
                       OR NOT EXISTS (SELECT 1 FROM jobs j3 WHERE j3.pipeline = 'recruiter' AND j3.target_id = cp.id))
                  AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.pipeline = 'recruiter' AND j.job_type = 'project_summary'
                                     AND j.target_type = 'candidate_project' AND j.target_id = cp.id
                                     AND j.run_number = %s AND j.status IN ('running', 'done'))""",
            (candidate_id, job.target_id, job.run_number, job.run_number)).fetchone()[0]
        if waiting == 0:
            conn.execute("UPDATE candidates SET status = 'reporting', status_detail = NULL, updated_at = now() "
                         "WHERE id = %s::uuid AND status NOT IN ('done', 'done_with_gaps', 'failed')", (candidate_id,))
    if waiting:
        save_partial_report(ctx.pool, candidate_id)
    started = []
    if waiting == 0:
        # The report is part of the same check run (a new resume is a new run), so a re-check builds a new report.
        started = queue.start_pipeline(ctx.pool, "recruiter_report", "candidate", candidate_id, job.run_number)
    return {"all_projects_finished": waiting == 0, "report_pipeline_started": bool(started)}
