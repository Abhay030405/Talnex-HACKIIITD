"""The Python steps of the self-test pipeline (python -> go -> python).
They prove a job can hop between the two kinds of worker and come back."""
from __future__ import annotations

import time
from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.db.usage import log_usage
from talnex_ai.worker.registry import JobContext, stage


@stage("selftest_a")
def selftest_a(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    # Also proves the worker can write usage_log, the table every model call is logged to.
    log_usage(ctx.pool, service="selftest", job_id=job.id, duration_ms=int((time.monotonic() - ctx.started) * 1000))
    return {"stage": "selftest_a", "runner": "python", "target": job.target_id}


@stage("selftest_c")
def selftest_c(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    return {"stage": "selftest_c", "runner": "python", "target": job.target_id}
