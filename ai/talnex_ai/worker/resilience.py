"""Keeps one stage from freezing a whole project.

The queue starts a stage only when every stage before it is done. A stage that fails on its last
try would leave everything after it waiting forever, and the project stuck in "testing". Optional
stages therefore use `never_stall`: while tries remain, a problem is raised so the queue tries
again; on the last try the stage ends as "skipped" with the reason, so the stages after it still
run and the result says plainly what didn't happen. A problem on our side is never a mark against
the project.
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, JobTimeout

log = logging.getLogger("talnex.stall")


def never_stall(fn: Callable[[Job, JobContext], Mapping[str, Any]]) -> Callable[[Job, JobContext], Mapping[str, Any]]:
    @functools.wraps(fn)
    def run(job: Job, ctx: JobContext) -> Mapping[str, Any]:
        try:
            return fn(job, ctx)
        except Exception as err:
            if job.max_tries and job.tries < job.max_tries:
                raise  # the queue will try again
            log.exception("stage %s failed on its last try", job.type)
            why = "ran out of time" if isinstance(err, JobTimeout) else f"hit a problem ({type(err).__name__})"
            return {"skipped": True,
                    "reason": f"this check {why} on every try, so it was left out",
                    "problem": str(err)[:300]}

    return run
