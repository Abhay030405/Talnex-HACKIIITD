import os
import time
import uuid

import pytest

from talnex_ai.claims.store import Subject
from talnex_ai.db import jobs as queue
from talnex_ai.worker.handlers.selftest import selftest_a
from talnex_ai.worker.handlers.video_read import video_read
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.runner import Worker
from talnex_ai.worker.subjects import (
    SubjectInfo, load_subject_info, set_status, stage_result, subject_of,
)


def make_worker(pool, handlers, **options):
    return Worker(pool, os.environ.get("TALNEX_TEST_DATABASE_URL", ""), handlers, worker_id="pytest",
                  retry_delay_seconds=0, **options)


def queued(pool, kind, target=None, **options):
    queue.enqueue_job(pool, kind, queue.RUNNER_PYTHON, "project", target or str(uuid.uuid4()), **options)
    return queue.take_job(pool, queue.RUNNER_PYTHON, "pytest-0")


def row(pool, job_id):
    with pool.connection() as conn:
        return conn.execute("SELECT status, result, error FROM jobs WHERE id = %s", (job_id,)).fetchone()


def test_a_good_handler_completes_the_job(pool):
    worker = make_worker(pool, {"echo": lambda job, ctx: {"saw": job.input["n"]}})
    job = queued(pool, "echo", input={"n": 7})
    worker.run_one("pytest-0", job)
    assert row(pool, job.id)[:2] == ("done", {"saw": 7})


def test_a_failing_handler_is_retried_with_its_error(pool):
    def broken(job, ctx):
        raise RuntimeError("model said no")

    job = queued(pool, "broken")
    make_worker(pool, {"broken": broken}).run_one("pytest-0", job)
    status, _, error = row(pool, job.id)
    assert status == "retrying" and error.startswith("RuntimeError: model said no")


@pytest.mark.parametrize("handlers, message", [
    ({}, "no handler for job type"),
    ({"odd": lambda job, ctx: ["not", "a", "dict"]}, "expected a dict"),
])
def test_unknown_jobs_and_bad_results_fail_clearly(pool, handlers, message):
    job = queued(pool, "odd", max_tries=1)
    make_worker(pool, handlers).run_one("pytest-0", job)
    status, _, error = row(pool, job.id)
    assert status == "failed" and message in error


def test_nothing_returned_counts_as_an_empty_result(pool):
    job = queued(pool, "quiet")
    make_worker(pool, {"quiet": lambda job, ctx: None}).run_one("pytest-0", job)
    assert row(pool, job.id)[:2] == ("done", {})


def test_the_running_worker_picks_up_new_jobs(pool):
    seen = []
    worker = make_worker(pool, {"echo": lambda job, ctx: seen.append(job.id) or {"ok": True}},
                         concurrency=2, poll_seconds=0.5)
    worker.start()
    try:
        ids = [queue.enqueue_job(pool, "echo", queue.RUNNER_PYTHON, "project", str(uuid.uuid4())) for _ in range(3)]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(row(pool, i)[0] != "done" for i in ids):
            time.sleep(0.1)
    finally:
        worker.stop(timeout=5)
    assert all(row(pool, i)[0] == "done" for i in ids)
    assert sorted(seen) == sorted(ids)  # each job ran exactly once


def test_selftest_writes_the_usage_log(pool):
    job = queued(pool, "selftest_a")
    assert selftest_a(job, JobContext(job, pool))["runner"] == "python"
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) FROM usage_log WHERE job_id = %s AND service = 'selftest'",
                            (job.id,)).fetchone()[0] == 1


@pytest.fixture
def subjects(pool):
    """A hackathon project with a video, and a resume project with blank links."""
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event = conn.execute(
            """INSERT INTO events (owner_id, name, mode, starts_at, ends_at, role_level)
               VALUES (%s, 'pytest event', 'open_theme', now() - interval '1 day', now(), 'junior') RETURNING id""",
            (user,)).fetchone()[0]
        project = conn.execute(
            """INSERT INTO projects (event_id, team_name, live_url, video_url)
               VALUES (%s, 'Team Rocket', 'https://Rocket.Example.com/app', 'https://v.test/demo') RETURNING id::text""",
            (event,)).fetchone()[0]
        candidate = conn.execute("INSERT INTO candidates (owner_id, role_level) VALUES (%s, 'mid') RETURNING id",
                                 (user,)).fetchone()[0]
        resume_project = conn.execute(
            """INSERT INTO candidate_projects (candidate_id, name, bullets, live_url, repo_url)
               VALUES (%s, 'Budget app', '{}', '  ', 'https://github.com/x/budget') RETURNING id::text""",
            (candidate,)).fetchone()[0]
    yield project, resume_project
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event,))
        conn.execute("DELETE FROM candidates WHERE id = %s", (candidate,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_one_description_for_both_kinds_of_subject(pool, subjects):
    project, resume_project = subjects
    info = load_subject_info(pool, Subject("project", project))
    assert (info.name, info.role_level, info.live_host) == ("Team Rocket", "junior", "rocket.example.com")
    other = load_subject_info(pool, Subject("candidate_project", resume_project))
    assert (other.name, other.role_level, other.live_url, other.live_host) == ("Budget app", "mid", None, "")
    assert other.repo_url == "https://github.com/x/budget"
    with pytest.raises(LookupError):
        load_subject_info(pool, Subject("project", str(uuid.uuid4())))


def test_status_only_changes_for_hackathon_projects(pool, subjects):
    project, resume_project = subjects
    set_status(pool, load_subject_info(pool, Subject("project", project)), "testing")
    set_status(pool, load_subject_info(pool, Subject("candidate_project", resume_project)), "testing")  # no-op
    with pool.connection() as conn:
        assert conn.execute("SELECT status FROM projects WHERE id = %s", (project,)).fetchone()[0] == "testing"
    with pytest.raises(ValueError, match="unknown project status"):
        set_status(pool, SubjectInfo(Subject("project", project), "", None, None, None, "fresher"), "partying")


def test_video_read_skips_honestly_and_shows_progress(pool, subjects):
    project, _ = subjects
    job = queued(pool, "video_read", target=project, pipeline="hackathon")
    result = video_read(job, JobContext(job, pool))
    assert result["skipped"] and "not built yet" in result["reason"] and result["video_url"] == "https://v.test/demo"
    with pool.connection() as conn:
        assert conn.execute("SELECT status FROM projects WHERE id = %s", (project,)).fetchone()[0] == "reading"


def test_later_stages_can_read_earlier_results(pool):
    target = str(uuid.uuid4())
    first = queued(pool, "precheck", target=target, pipeline="hackathon")
    queue.complete_job(pool, first.id, "pytest-0", {"alive": True})
    later = queued(pool, "claims", target=target, pipeline="hackathon")
    assert stage_result(pool, later, "precheck") == {"alive": True}
    assert stage_result(pool, later, "live_test") is None
    with pytest.raises(ValueError, match="not a 'event'"):
        subject_of(queue.Job(**{**later.__dict__, "target_type": "event"}))
