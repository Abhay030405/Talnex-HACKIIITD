"""Job `tour_message`: answer one message of a guided tour (architecture section 32).

Added by the Go API with no pipeline (input {"message_id": ...}), so finishing it never starts another stage. One try only:
a second try would open a second paid browser. The message always ends 'done' or 'failed', never stuck on 'working'.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.reports.walkthrough.tour.answer import answer_message
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services


@stage("tour_message")
def tour_message(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    message_id = str(job.input.get("message_id") or "")
    if not message_id:
        raise ValueError("tour_message needs a message_id")
    return answer_message(get_services(ctx.pool), message_id, job_id=job.id, check_time=ctx.check)
