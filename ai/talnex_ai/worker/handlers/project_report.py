"""Stage `project_report` (hackathon): build one project's proof card and save it, replacing any earlier card.

The last stage of a hackathon project. The website reads the saved card through the Go API (owner
only, with short-lived links for the proof files). Building it again after a re-run replaces it.
When the last team of an event gets here, this stage also starts the event-level checks.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from talnex_ai.db import jobs as queue
from talnex_ai.db.jobs import Job
from talnex_ai.reports.project_card import build_project_card
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.subjects import subject_of


def save_card(pool, project_id: str) -> dict:
    """Build a project's proof card and save it, replacing the earlier one."""
    card = build_project_card(pool, project_id)
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO project_reports (project_id, report, has_gaps, generated_at) VALUES (%s::uuid, %s::jsonb, %s, now())
               ON CONFLICT (project_id) DO UPDATE SET report = EXCLUDED.report, has_gaps = EXCLUDED.has_gaps, generated_at = now()""",
            (project_id, json.dumps(card), card["has_gaps"]))
    return card


def start_event_checks(pool, project_id: str) -> bool:
    """When the last team of an event has reached its report, start the event-level checks (copying,
    comparison, AI opinion). A team has "reached" it when its report job is running or done, so two
    teams finishing together can't both think the other is still waiting; starting twice adds nothing,
    because the job key holds the event and the run number."""
    with pool.connection() as conn:
        event_id = conn.execute("SELECT event_id::text FROM projects WHERE id = %s::uuid", (project_id,)).fetchone()[0]
        waiting = conn.execute(
            """SELECT count(*) FROM projects p WHERE p.event_id = %s::uuid
                 AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.pipeline = 'hackathon' AND j.job_type = 'project_report'
                                    AND j.target_type = 'project' AND j.target_id = p.id
                                    AND j.status IN ('running', 'done'))""", (event_id,)).fetchone()[0]
        if waiting:
            return False
        run = conn.execute(
            """SELECT coalesce(max(run_number), 1) FROM jobs
                WHERE pipeline = 'hackathon' AND job_type = 'project_report' AND target_type = 'project'
                  AND target_id IN (SELECT id FROM projects WHERE event_id = %s::uuid)""", (event_id,)).fetchone()[0]
    return bool(queue.start_pipeline(pool, "hackathon_event", "event", event_id, run))


@stage("project_report")
@never_stall
def project_report(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    if subject.kind != "project":
        return {"skipped": True, "reason": "the proof card is for hackathon projects"}
    card = save_card(ctx.pool, subject.id)
    return {"features": len(card["features"]), "groups": len(card["groups"]), "flags": len(card["flags"]),
            "has_gaps": card["has_gaps"], "event_checks_started": start_event_checks(ctx.pool, subject.id)}
