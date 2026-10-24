import uuid

import psycopg
import pytest

from talnex_ai.db import jobs
from talnex_ai.db.usage import log_usage

PIPE = "pytest_pipe"


@pytest.fixture
def two_stage_pipeline(pool):
    """first -> second, both Python stages on a project."""
    with pool.connection() as conn:
        conn.execute("DELETE FROM pipeline_stages WHERE pipeline = %s", (PIPE,))
        conn.execute(
            """INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages) VALUES
               (%s, 'first', 'python', 'project', '{}'), (%s, 'second', 'python', 'project', '{first}')""",
            (PIPE, PIPE),
        )
    yield PIPE
    with pool.connection() as conn:
        conn.execute("DELETE FROM jobs WHERE pipeline = %s", (PIPE,))
        conn.execute("DELETE FROM pipeline_stages WHERE pipeline = %s", (PIPE,))


def test_job_from_row():
    job_id, target = uuid.uuid4(), uuid.uuid4()
    job = jobs.Job.from_row({
        "id": job_id, "job_type": "claims", "runner": "python", "target_type": "project",
        "target_id": target, "input": None, "pipeline": None, "run_number": 1, "tries": 1,
        "max_tries": 3, "time_limit_seconds": 900,
    })
    assert job.id == str(job_id) and job.target_id == str(target)
    assert job.type == "claims" and job.input == {}


def test_usage_write_failure_does_not_raise():
    class BrokenPool:
        def connection(self):
            raise psycopg.OperationalError("database went away")

    assert log_usage(BrokenPool(), service="openrouter", model="m") is False


def test_enqueue_take_complete(pool, target_id):
    job_id = jobs.enqueue_job(pool, "selftest", jobs.RUNNER_PYTHON, "project", target_id, input={"n": 1})
    assert job_id
    assert jobs.enqueue_job(pool, "selftest", jobs.RUNNER_PYTHON, "project", target_id) is None

    job = jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert job.id == job_id and job.input == {"n": 1} and job.tries == 1
    assert jobs.take_job(pool, jobs.RUNNER_PYTHON, "w2") is None
    assert jobs.take_job(pool, jobs.RUNNER_GO, "g1") is None

    assert jobs.complete_job(pool, job_id, "w1", {"ok": True}) == []
    with pool.connection() as conn:
        status, result = conn.execute("SELECT status, result FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert status == "done" and result == {"ok": True}


def test_only_the_holder_can_finish_a_job(pool, target_id):
    job_id = jobs.enqueue_job(pool, "selftest", jobs.RUNNER_PYTHON, "project", target_id)
    jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert jobs.fail_job(pool, job_id, "someone-else", "nope") is None
    assert jobs.complete_job(pool, job_id, "someone-else") == []
    with pool.connection() as conn:
        assert conn.execute("SELECT status FROM jobs WHERE id = %s", (job_id,)).fetchone()[0] == "running"


def test_fail_retries_then_gives_up(pool, target_id):
    job_id = jobs.enqueue_job(pool, "selftest", jobs.RUNNER_PYTHON, "project", target_id, max_tries=2)
    jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert jobs.fail_job(pool, job_id, "w1", "boom", delay_seconds=0) == "retrying"
    jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert jobs.fail_job(pool, job_id, "w1", "boom again", delay_seconds=0) == "failed"
    assert jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1") is None


def test_retry_waits_before_it_can_be_taken(pool, target_id):
    job_id = jobs.enqueue_job(pool, "selftest", jobs.RUNNER_PYTHON, "project", target_id)
    jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert jobs.fail_job(pool, job_id, "w1", "slow down", delay_seconds=60) == "retrying"
    assert jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1") is None


def test_pipeline_queues_next_stage_on_complete(two_stage_pipeline, pool, target_id):
    started = jobs.start_pipeline(pool, two_stage_pipeline, "project", target_id)
    assert len(started) == 1
    first = jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert first.type == "first" and first.pipeline == two_stage_pipeline

    added = jobs.complete_job(pool, first.id, "w1")
    assert len(added) == 1
    second = jobs.take_job(pool, jobs.RUNNER_PYTHON, "w1")
    assert second.id == added[0] and second.type == "second"
    assert jobs.start_pipeline(pool, two_stage_pipeline, "project", target_id) == []


def test_usage_row_is_written(pool, target_id):
    job_id = jobs.enqueue_job(pool, "selftest", jobs.RUNNER_PYTHON, "project", target_id)
    assert log_usage(pool, service="openrouter", model="some/model", job_id=job_id,
                     tokens_in=120, tokens_out=40, duration_ms=900, cost_usd=0.0012)
    with pool.connection() as conn:
        row = conn.execute("SELECT service, model, tokens_in, cost_usd FROM usage_log WHERE job_id = %s",
                           (job_id,)).fetchone()
    assert row[0] == "openrouter" and row[1] == "some/model" and row[2] == 120
    assert float(row[3]) == pytest.approx(0.0012)
