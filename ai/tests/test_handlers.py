"""The wire-up: every stage registered, the shared services, and the claims and feature_score stages.

Real database; scripted stand-ins for the model and TinyFish."""
import json
import os
import uuid
from pathlib import Path

import pytest

from talnex_ai import settings
from talnex_ai.claims.store import Subject, load_claims
from talnex_ai.db import jobs as queue
from talnex_ai.testing.runner import driver
from talnex_ai.worker import handlers as _stages  # noqa: F401  (registers every stage)
from talnex_ai.worker.handlers import feature_score as score_module
from talnex_ai.worker.registry import JobContext, handlers
from talnex_ai.worker.services import Services, build_services, get_services, set_services
from tests.fakes import FakeFiles, FakeTinyFish, Reply

CHECKLIST = {"items": [{"text": "a todo is added", "part": "implementation", "core": True},
                       {"text": "the count updates", "part": "logic"},
                       {"text": "empty text is refused", "part": "edge"}]}


class Model:
    """Plays the claim reader and the checklist marker, and counts the calls."""

    def __init__(self, claims=(), marks=("present", "present", "missing")):
        self.claims, self.marks, self.calls = list(claims), list(marks), []

    def chat(self, role, messages, **_):
        self.calls.append(role)
        if "claims" in messages[0]["content"].lower() and self.claims:
            return Reply(json.dumps({"claims": self.claims}))
        return Reply(json.dumps({"marks": [{"index": i, "status": s, "note": "step 2"} for i, s in enumerate(self.marks, 1)],
                                 "mechanism_present": None}))


@pytest.fixture(autouse=True)
def clear_services():
    yield
    set_services(None)


def install(pool, model=None, cfg=None):
    sv = Services(cfg, pool, model or Model(), FakeTinyFish(), FakeFiles(), lambda host: None, Path("testdata"))
    set_services(sv)
    return sv


def job_for(pool, stage, target_type, target_id, pipeline="hackathon", result=None, status="running"):
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, dedupe_key,
                                 locked_by, locked_at, tries, result)
               VALUES (%s, 'python', %s, %s::uuid, %s, 1, %s, %s, 'w', now(), 1, %s::jsonb) RETURNING id::text""",
            (stage, target_type, target_id, pipeline, status, f"{pipeline}:{stage}:{target_id}:{uuid.uuid4()}",
             json.dumps(result) if result is not None else None)).fetchone()
    return queue.Job(id=row[0], type=stage, runner="python", target_type=target_type, target_id=target_id, input={},
                     pipeline=pipeline, run_number=1, tries=1, max_tries=3, time_limit_seconds=900)


def run(pool, stage, target_type, target_id, pipeline="hackathon"):
    job = job_for(pool, stage, target_type, target_id, pipeline)
    return handlers()[stage](job, JobContext(job, pool))


# ------------------------------------------------------------------ registry and services


def test_every_python_stage_of_every_pipeline_has_a_handler(pool):
    with pool.connection() as conn:
        wanted = {r[0] for r in conn.execute("SELECT DISTINCT stage FROM pipeline_stages WHERE runner = 'python'")}
    missing = wanted - set(handlers())
    assert not missing, f"stages with no Python handler: {sorted(missing)}"
    assert {"claims", "feature_score", "ai_opinion", "selftest_a"} <= set(handlers())


def test_installed_services_are_the_ones_handed_out(pool):
    sv = install(pool)
    assert get_services(pool) is sv and sv.connect is driver.connect and sv.sandbox is None
    assert sv.mailbox_for("example.com") is None


def test_real_services_build_from_the_settings(pool, base_env):
    endpoint = os.environ.get("TALNEX_TEST_S3_ENDPOINT", "").strip()
    if not endpoint:
        pytest.skip("TALNEX_TEST_S3_ENDPOINT is not set")
    cfg = settings.load({**base_env, "S3_ENDPOINT": endpoint, "S3_BUCKET": f"pytest-{uuid.uuid4().hex[:8]}",
                         "S3_ACCESS_KEY": os.environ["TALNEX_TEST_S3_ACCESS_KEY"],
                         "S3_SECRET_KEY": os.environ["TALNEX_TEST_S3_SECRET_KEY"],
                         "OPENROUTER_API_KEY": "k", "TINYFISH_API_KEY": "k"})
    sv = build_services(pool, cfg)
    assert sv.files.client.bucket_exists(cfg.s3.bucket)                  # the bucket is made at start
    assert sv.mailbox_for("site.test") is None and sv.smsbox_for("site.test") is None   # email and phone are off
    assert sv.uploads_root == Path("testdata") and not cfg.sandbox.enabled and sv.sandbox is not None


# ------------------------------------------------------------------ claims


@pytest.fixture
def event(pool):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]

    def make(mode="fixed_problem", repo=None):
        with pool.connection() as conn:
            event = conn.execute("""INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
                                    VALUES (%s, 'Wire Hack', %s, now() - interval '1 day', now()) RETURNING id""",
                                 (user, mode)).fetchone()[0]
            conn.execute("INSERT INTO criteria (event_id, name, description, weight) VALUES (%s, 'Search', 'find recipes', 3)",
                         (event,))
            return conn.execute("INSERT INTO projects (event_id, team_name, live_url, repo_url) VALUES (%s, 'Ants', 'https://ants.test', %s) "
                                "RETURNING id::text", (event, repo)).fetchone()[0]

    yield make
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE owner_id = %s", (user,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_criteria_become_claims_once_and_a_rerun_reuses_them(pool, event):
    project = event()
    model = Model(claims=[{"text": "Search recipes by an ingredient", "claim_group": "Search", "importance": 3,
                           "source": "criteria"}])
    install(pool, model)
    first = run(pool, "claims", "project", project)
    assert first["claims"] == 1 and first["reused"] is False
    assert [c.text for c in load_claims(pool, Subject("project", project))] == ["Search recipes by an ingredient"]
    calls = len(model.calls)
    assert run(pool, "claims", "project", project) == {"claims": 1, "reused": True}
    assert len(model.calls) == calls                                       # no new reading, so the runs compare


def test_an_open_theme_project_without_a_repo_or_sandbox_is_skipped_with_the_reason(pool, event, base_env):
    install(pool, cfg=settings.load(base_env))
    out = run(pool, "claims", "project", event(mode="open_theme"))
    assert out["skipped"] and "no repository link" in out["reason"]
    out = run(pool, "claims", "project", event(mode="open_theme", repo="https://github.com/a/b"))
    assert out["skipped"] and "sandbox host is not set up" in out["reason"]


def test_claims_refuse_a_target_that_is_not_a_project(pool):
    install(pool)
    with pytest.raises(ValueError, match="project or a candidate_project"):
        run(pool, "claims", "event", str(uuid.uuid4()))


# ------------------------------------------------------------------ feature_score


@pytest.fixture
def tested(pool, event):
    """A project with a tested claim (a main run and an extra check) and one that could not be tested."""
    project = event()
    with pool.connection() as conn:
        ids = {}
        for text, verdict in (("Add a todo", "works"), ("Share a list", "could_not_test")):
            ids[text] = conn.execute("""INSERT INTO claims (project_id, text, claim_group, importance, source)
                                        VALUES (%s, %s, 'Core', 2, 'criteria') RETURNING id::text""", (project, text)).fetchone()[0]
            conn.execute("INSERT INTO results (claim_id, verdict, confidence, reason) VALUES (%s, %s, 'high', 'seen on screen')",
                         (ids[text], verdict))
        for kind, outcome, action in (("normal", "passed", "typed 'milk' and pressed Enter"),
                                      ("bad_input", "passed", "pressed Enter with no text")):
            run_id = conn.execute("""INSERT INTO test_runs (claim_id, track, test_type, outcome, started_at)
                                     VALUES (%s, 'live', %s, %s, now()) RETURNING id""", (ids["Add a todo"], kind, outcome)).fetchone()[0]
            conn.execute("INSERT INTO steps (run_id, step_number, kind, action, observed) VALUES (%s, 1, 'screen', %s, 'as expected')",
                         (run_id, action))
    return project, ids


def test_the_evidence_shows_the_main_run_and_the_extra_checks(pool, tested):
    _, ids = tested
    verdict, confidence, reason, evidence = score_module.evidence_text(pool, ids["Add a todo"])
    assert (verdict, confidence, reason) == ("works", "high", "seen on screen")
    assert evidence.index("Steps of the main test run") < evidence.index("typed 'milk'") < evidence.index("Extra check (bad input)")


def test_tested_features_are_scored_and_untested_ones_left_out(pool, tested):
    project, ids = tested
    job_for(pool, "test_plan", "project", project, result={"claims": {ids["Add a todo"]: {"checklist": CHECKLIST}}}, status="done")
    model = Model()
    install(pool, model)
    out = run(pool, "feature_score", "project", project)
    assert out["features_scored"] == 1 and out["of"] == 2 and out["not_scored"] == ["Share a list"]
    assert len(model.calls) == 1                                           # the checklist came from test_plan: one marking call
    with pool.connection() as conn:
        score, why = conn.execute("SELECT feature_score, score_reason FROM results WHERE claim_id = %s::uuid",
                                  (ids["Add a todo"],)).fetchone()
        talnex = conn.execute("SELECT score, coverage FROM scores WHERE project_id = %s::uuid AND score_group = 'talnex'",
                              (project,)).fetchone()
    assert score is not None and why
    assert talnex is not None and float(talnex[1]) == 50.0                 # half the testable features were scored
