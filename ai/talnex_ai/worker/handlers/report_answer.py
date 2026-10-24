"""Job `report_answer` (Ask TalNex): answer one recruiter question about a candidate from the saved proof report.

Added by the Go API with no pipeline (input {"question": ...}); the answer is the job's result. Safe to run twice.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, Field

from talnex_ai.db.jobs import Job
from talnex_ai.formats import parse_model
from talnex_ai.llm.prompts import report_answer as prompt
from talnex_ai.llm.structured import ask_json
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services
from talnex_ai.claims.store import Subject
from talnex_ai.reports.project_card import build_project_card
from talnex_ai.worker.subjects import load_subject_info, role_brief

MAX_REPORT_CHARS = 24000


class Action(BaseModel):
    type: Literal["rerun_project", "rerun_coding", "change_weight"]
    project: Optional[str] = None
    criterion: Optional[str] = None
    weight: Optional[float] = Field(default=None, gt=0, le=1000)


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    action: Optional[Action] = None


def slim(report: Mapping[str, Any]) -> str:
    """The report without proof files and step-by-step details, so it fits the prompt."""
    def lean(features):
        return [{k: v for k, v in f.items() if k not in ("proof", "observations", "code_review")} for f in features or []]

    keep = dict(report)
    if "projects" in report:
        keep["projects"] = [{**p, "features": lean(p.get("features"))} for p in report.get("projects") or []]
    if "features" in report:   # a hackathon proof card
        keep["features"] = lean(report.get("features"))
    return json.dumps(keep, default=str)[:MAX_REPORT_CHARS]


@stage("report_answer")
def report_answer(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    question = str((job.input or {}).get("question") or "").strip()
    if not question:
        return {"answer": "No question was asked.", "action": None}
    with ctx.pool.connection() as conn:
        if job.target_type == "project":
            # A hackathon project: its saved proof card, with the event brief and team abstract as the brief.
            stored = conn.execute("SELECT report FROM project_reports WHERE project_id = %s::uuid", (job.target_id,)).fetchone()
            row = (stored[0] if stored else None, None)
        else:
            row = conn.execute("""SELECT r.report, c.role_id::text FROM candidates c
                                    LEFT JOIN candidate_reports r ON r.candidate_id = c.id WHERE c.id = %s::uuid""",
                               (job.target_id,)).fetchone()
        brief = role_brief(conn, row[1]) if row and row[1] else ""
        history = [(q, a) for q, a in reversed(conn.execute(
            """SELECT input->>'question', result->>'answer' FROM jobs WHERE job_type = 'report_answer' AND target_id = %s::uuid
                AND status = 'done' AND id <> %s::uuid ORDER BY created_at DESC LIMIT 6""", (job.target_id, job.id)).fetchall())
                   if q and a]
    if job.target_type == "project":
        if not row[0]:
            row = (build_project_card(ctx.pool, job.target_id), None)   # not saved yet: build it from the results so far
        brief = load_subject_info(ctx.pool, Subject("project", job.target_id)).brief
    if not row or not row[0]:
        return {"answer": "There is no report yet. Ask again once the first project has been checked.", "action": None}
    got = ask_json(get_services(ctx.pool).model, "claim_reader", prompt.SYSTEM, prompt.build_user(question, slim(row[0]), brief, history),
                   lambda text: parse_model(Answer, text), job_id=job.id, temperature=0.2)
    return got.model_dump()
