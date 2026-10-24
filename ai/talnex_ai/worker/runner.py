"""The worker loop.

Several threads each take the next Python job from the queue, run its handler and report the
result. A separate listener wakes them the moment Postgres announces a new Python job, so a job
starts within milliseconds instead of waiting for the next poll.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any, Mapping, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.db import jobs as queue
from talnex_ai.live import NullEmitter, for_job
from talnex_ai.worker.registry import Handler, JobContext, JobTimeout

log = logging.getLogger("talnex.worker")

SAVE_TRIES = 3  # a finished job's result is worth a couple of retries: it may have cost real money



# Which role check each stage belongs to (the recruiter picks checks on the new-role form). Stages not listed always run.
STAGE_CHECK = {"live_test": "live_test", "code_review": "code_review", "authorship_read": "code_review",
               "codechef": "coding_profiles", "leetcode": "coding_profiles", "leetcode_replay": "coding_profiles"}


def check_turned_off(pool, job) -> "str | None":
    """The role check that turns this stage off for its candidate, or None. An empty checks set means every check."""
    check = STAGE_CHECK.get(job.type)
    if check is None or job.target_type not in ("candidate", "candidate_project"):
        return None
    candidate = "c.id = %s::uuid" if job.target_type == "candidate" else         "c.id = (SELECT candidate_id FROM candidate_projects WHERE id = %s::uuid)"
    with pool.connection() as conn:
        row = conn.execute(f"SELECT r.checks FROM candidates c JOIN roles r ON r.id = c.role_id WHERE {candidate}",
                           (job.target_id,)).fetchone()
    checks = (row[0] if row else None) or {}
    return check if checks and checks.get(check) is False else None

class Worker:
    def __init__(
        self,
        pool: ConnectionPool,
        database_url: str,
        handlers: Mapping[str, Handler],
        *,
        worker_id: str,
        concurrency: int = 5,
        poll_seconds: float = 5.0,
        retry_delay_seconds: int = 30,
        live_events: bool = True,
    ):
        self.pool = pool
        self.live_events = live_events  # send stage events to the live view (docs/live_events.md)
        self.database_url = database_url
        self.handlers = dict(handlers)
        self.worker_id = worker_id
        self.concurrency = max(1, concurrency)
        self.poll_seconds = poll_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.stop_event = threading.Event()
        self._wake = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- starting and stopping ----

    def start(self) -> None:
        self._threads = [threading.Thread(target=self._listen, name="listener", daemon=True)]
        for n in range(self.concurrency):
            self._threads.append(threading.Thread(target=self._loop, args=(f"{self.worker_id}-{n}",),
                                                  name=f"worker-{n}", daemon=True))
        for thread in self._threads:
            thread.start()

    def stop(self, timeout: Optional[float] = 30) -> None:
        """Ask every thread to finish its current job and stop."""
        self.stop_event.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=timeout)

    def run_forever(self) -> None:
        self.start()
        try:
            while not self.stop_event.is_set():
                self.stop_event.wait(1)
        finally:
            self.stop()

    # ---- the loop ----

    def _loop(self, worker: str) -> None:
        while not self.stop_event.is_set():
            try:
                job = queue.take_job(self.pool, queue.RUNNER_PYTHON, worker)
            except Exception:
                log.exception("could not take a job; trying again shortly")
                self.stop_event.wait(self.poll_seconds)
                continue
            if job is not None:
                self.run_one(worker, job)
                continue  # there may be more work: look again straight away
            if self._wake.wait(self.poll_seconds):
                self._wake.clear()

    def run_one(self, worker: str, job: queue.Job) -> None:
        """Run one job's handler and report the outcome to the queue. Never raises."""
        handler = self.handlers.get(job.type)
        if handler is None:
            self._fail(worker, job, f"no handler for job type {job.type!r}")
            return

        ctx = JobContext(job, self.pool)
        events = for_job(self.pool, job) if self.live_events else NullEmitter()
        events.emit("stage.started", try_number=job.tries)
        try:
            off = check_turned_off(self.pool, job) if self.pool is not None else None
            result = {"skipped": True, "reason": f"not run: {off} was not chosen for this role"} if off else handler(job, ctx)
            ctx.check()  # a result that arrives after the time limit doesn't count
            if result is None:
                result = {}
            if not isinstance(result, Mapping):
                raise TypeError(f"handler returned {type(result).__name__}, expected a dict")
        except JobTimeout as err:
            events.emit("stage.failed", status=self._fail(worker, job, str(err)), error=str(err))
            return
        except Exception as err:  # one handler's failure must never stop the worker
            status = self._fail(worker, job, f"{type(err).__name__}: {err}\n{traceback.format_exc(limit=8)}")
            events.emit("stage.failed", status=status, error=f"{type(err).__name__}: {err}")
            return
        self._complete(worker, job, result, ctx)
        events.emit("stage.finished", seconds=round(time.monotonic() - ctx.started, 1),
                    skipped=bool(result.get("skipped")), reason=result.get("reason"))

    def _complete(self, worker: str, job: queue.Job, result: Mapping[str, Any], ctx: JobContext) -> None:
        for attempt in range(1, SAVE_TRIES + 1):
            try:
                added = queue.complete_job(self.pool, job.id, worker, result)
            except Exception:
                if attempt == SAVE_TRIES:
                    # The job stays "running"; the reaper hands it back once its time limit passes.
                    log.exception("could not save the result of job %s", job.id)
                    return
                self.stop_event.wait(attempt)
                continue
            log.info("job done id=%s type=%s took=%.2fs next_jobs=%d", job.id, job.type,
                     time.monotonic() - ctx.started, len(added))
            return

    def _fail(self, worker: str, job: queue.Job, message: str) -> Optional[str]:
        """Record a failure. Returns the job's new status (retrying or failed), or None if it couldn't be saved."""
        try:
            status = queue.fail_job(self.pool, job.id, worker, message, self.retry_delay_seconds)
            log.warning("job failed id=%s type=%s now=%s: %s", job.id, job.type, status, message.splitlines()[0])
            return status
        except Exception:
            log.exception("could not record the failure of job %s", job.id)
            return None

    # ---- wake-up signal ----

    def _listen(self) -> None:
        """Wake the loops the moment a Python job is queued (Postgres NOTIFY on channel "jobs")."""
        import psycopg

        while not self.stop_event.is_set():
            try:
                with psycopg.connect(self.database_url, autocommit=True) as conn:
                    conn.execute("LISTEN jobs")
                    while not self.stop_event.is_set():
                        for note in conn.notifies(timeout=1.0, stop_after=1):
                            if note.payload == queue.RUNNER_PYTHON:
                                self._wake.set()
            except Exception:
                if not self.stop_event.is_set():
                    log.warning("the job listener dropped; reconnecting", exc_info=True)
                    self.stop_event.wait(3)
