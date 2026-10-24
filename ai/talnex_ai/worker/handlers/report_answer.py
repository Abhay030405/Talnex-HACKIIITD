"""Job `report_answer` (Ask TalNex): answer one recruiter question about a candidate from the saved proof report.

Added by the Go API with no pipeline (input {"question": ...}); the answer is the job's result. Safe to run twice.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from talnex_ai.coding.leetcode_signals import read_graphql
from talnex_ai.db.jobs import Job
from talnex_ai.formats import FormatError
from talnex_ai.formats.parse import parse_json_block
from talnex_ai.reports.ask_tools import GitHubReader, ToolRefused, Tools, codeforces_reader, scope_for
from talnex_ai.llm.prompts import report_answer as prompt
from talnex_ai.llm.structured import ask_json
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services
from talnex_ai.claims.store import Subject
from talnex_ai.reports.project_card import build_project_card
from talnex_ai.worker.subjects import load_subject_info, role_brief

MAX_REPORT_CHARS = 24000
MAX_TOOL_CALLS = 4


class Action(BaseModel):
    type: Literal["rerun_project", "rerun_coding", "change_weight", "custom_test"]
    project: Optional[str] = None
    instruction: Optional[str] = Field(default=None, max_length=500)
    criterion: Optional[str] = None
    weight: Optional[float] = Field(default=None, gt=0, le=1000)


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    action: Optional[Action] = None


class ToolCall(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)


def parse_reply(text: str) -> Union[ToolCall, Answer]:
    """A tool call ({"tool": ...}) or the final answer."""
    data = parse_json_block(text)
    model = ToolCall if isinstance(data, dict) and "tool" in data else Answer
    try:
        return model.model_validate(data)
    except ValidationError as err:
        raise FormatError(str(err).splitlines()[0]) from err


def answer_with_tools(ask: Callable[[str], Union[ToolCall, Answer]], tools: Tools, base_user: str,
                      max_calls: int = MAX_TOOL_CALLS) -> tuple[Answer, list[dict]]:
    """Let the model call read-only tools (at most `max_calls`) before it answers. Returns the answer and its sources."""
    results: list[tuple[str, str, str]] = []
    sources: list[dict] = []
    for turn in range(max_calls + 1):
        user = base_user + "\n\n" + prompt.tool_section(tools.scope.describe(), results)
        if turn == max_calls:
            user += "\n\n" + prompt.TOOLS_DONE
        reply = ask(user)
        if isinstance(reply, Answer):
            return reply, sources
        if turn == max_calls:
            break
        try:
            text, what = tools.run(reply.tool, reply.args)
            sources.append({"tool": reply.tool, "what": what, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        except ToolRefused as err:
            text, what = f"refused: {err}", "refused"
        except Exception as err:   # a site or API being down must never break the answer
            text, what = f"could not read: {type(err).__name__}", "failed"
        results.append((reply.tool, what, text))
    return Answer(answer="I could not finish looking that up. Please ask again.", action=None), sources


def make_tools(pool, job: Job) -> Tools:
    """The real read-only tools, limited to this subject's repositories, sites and handles."""
    sv = get_services(pool)
    cfg = sv.cfg
    lc_url = getattr(cfg, "leetcode_graphql_url", "") if cfg else ""
    return Tools(
        scope_for(pool, job.target_type, job.target_id),
        github=GitHubReader(getattr(cfg, "github_api_base_url", "https://api.github.com"), getattr(cfg, "github_token", "")),
        fetch=lambda urls: sv.tinyfish.fetch(urls, fmt="markdown"),
        leetcode=(lambda handle: read_graphql(lc_url, handle)) if lc_url else None,
        codeforces=codeforces_reader(getattr(cfg, "codeforces_api_base_url", "https://codeforces.com/api")),
    )


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
    model = get_services(ctx.pool).model
    got, sources = answer_with_tools(
        lambda user: ask_json(model, "claim_reader", prompt.SYSTEM, user, parse_reply, job_id=job.id, temperature=0.2),
        make_tools(ctx.pool, job), prompt.build_user(question, slim(row[0]), brief, history))
    return {**got.model_dump(), "sources": sources}
