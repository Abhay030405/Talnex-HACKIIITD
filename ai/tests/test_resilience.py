import time

import pytest

from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, JobTimeout, handlers, stage
from talnex_ai.worker.resilience import never_stall


def job(tries=1, max_tries=3, limit=900, kind="sandbox_run"):
    return Job(id="j1", type=kind, runner="python", target_type="project", target_id="p1", input={},
               pipeline="hackathon", run_number=1, tries=tries, max_tries=max_tries, time_limit_seconds=limit)


def test_stages_register_once():
    @stage("pytest_stage_once")
    def first(job, ctx):
        return {}

    assert handlers()["pytest_stage_once"] is first
    stage("pytest_stage_once")(first)  # the same function again is harmless (e.g. a module reloaded)
    with pytest.raises(ValueError, match="two handlers"):
        stage("pytest_stage_once")(lambda job, ctx: {})


def test_context_stops_at_the_time_limit():
    ctx = JobContext(job(limit=60), started=time.monotonic() - 61)
    assert ctx.remaining() < 0
    with pytest.raises(JobTimeout, match="60s time limit"):
        ctx.check()
    JobContext(job(limit=60)).check()


@never_stall
def flaky(job, ctx):
    raise ConnectionError("sandbox host unreachable")


def test_never_stall_lets_the_queue_retry_while_tries_remain():
    with pytest.raises(ConnectionError):
        flaky(job(tries=1, max_tries=3), JobContext(job()))


def test_never_stall_skips_on_the_last_try_so_later_stages_run():
    result = flaky(job(tries=3, max_tries=3), JobContext(job()))
    assert result["skipped"] is True
    assert "hit a problem (ConnectionError)" in result["reason"] and "left out" in result["reason"]
    assert result["problem"] == "sandbox host unreachable"


def test_never_stall_names_a_timeout_plainly():
    @never_stall
    def slow(job, ctx):
        raise JobTimeout("too slow")

    assert "ran out of time" in slow(job(tries=3, max_tries=3), JobContext(job()))["reason"]


def test_never_stall_passes_good_results_through():
    assert never_stall(lambda job, ctx: {"ok": 1})(job(), JobContext(job())) == {"ok": 1}
