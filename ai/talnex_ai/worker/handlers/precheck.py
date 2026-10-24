"""Stage `precheck`: do the project's live link and repository open? (A free TinyFish Fetch.)

Works the same for a hackathon project and a project on a resume. A link that doesn't load is a flag
("required item missing"), never a mark against the work; later stages just have nothing to test.
Text aimed at an AI checker found on the page becomes a "hidden AI instructions" flag.
"""
from __future__ import annotations

from typing import Any, Mapping

from psycopg_pool import ConnectionPool

from talnex_ai.db.jobs import Job
from talnex_ai.safety.hidden_instructions import find_hidden_instructions
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import SubjectInfo, load_subject_info, set_status, subject_of

_WHAT = {"live": "live link", "repo": "repository link"}


def precheck_subject(pool: ConnectionPool, tinyfish: Any, info: SubjectInfo) -> dict[str, Any]:
    """Fetch the subject's links, raise flags for dead links and hidden instructions, and return what was found."""
    wanted = {"live": info.live_url, "repo": info.repo_url}
    result: dict[str, Any] = {"live": None, "repo": None}
    urls = [u for u in wanted.values() if u]
    if not urls:
        add_flag(pool, info.kind, info.id, "required_item_missing", "info",
                 "No live link or repository link was given, so there is nothing to test")
        return result

    fetched = dict(zip(urls, tinyfish.fetch(urls)))
    for name, url in wanted.items():
        if not url:
            continue
        page = fetched[url]
        result[name] = {"url": url, "ok": page.ok, "error_code": page.error_code, "http_status": page.http_status,
                        "title": page.title}
        if not page.ok:
            add_flag(pool, info.kind, info.id, "required_item_missing", "info",
                     f"The {_WHAT[name]} did not load ({page.error_code or 'no answer'})",
                     {"url": url, "http_status": page.http_status})
            continue
        for finding in find_hidden_instructions(page.text):
            if finding.level in ("strong", "review"):
                add_flag(pool, info.kind, info.id, "hidden_ai_instructions", finding.level,
                         f"Text aimed at an AI checker was found on the {_WHAT[name]}",
                         {"url": url, **finding.as_flag_evidence()})
    return result


@stage("precheck")
def precheck(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    info = load_subject_info(ctx.pool, subject_of(job))
    set_status(ctx.pool, info, "prechecking")
    result = precheck_subject(ctx.pool, get_services(ctx.pool).tinyfish, info)
    ctx.check()
    return result
