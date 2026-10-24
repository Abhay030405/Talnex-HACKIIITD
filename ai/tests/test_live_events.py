import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from talnex_ai import settings
from talnex_ai.claims.store import Subject
from talnex_ai.db import jobs as queue
from talnex_ai.formats import Claim, TestPlan
from talnex_ai.live import events as live
from talnex_ai.live import Emitter, NullEmitter, for_job
from talnex_ai.live.watch import describe
from talnex_ai.testing.runner.executor import ExecConfig, execute_plan
from talnex_ai.worker.handlers.live_test import live_test_subject
from talnex_ai.worker.runner import Worker
from talnex_ai.worker.subjects import SubjectInfo
from tests.fakes import FakeDriver, FakeFiles, FakeTinyFish, ScriptedModel, act, connector, done, verdict

PLAN = TestPlan.model_validate({"test_type": "normal", "expected_result": "the todo is listed",
                                "steps": [{"action": "add a todo", "expected": "it is listed"}]})


class Recorder:
    """Stands in for an Emitter and keeps every event, with the context children add."""

    def __init__(self, sink=None, **context):
        self.sink = sink if sink is not None else []
        self.context = context

    def child(self, **context):
        return Recorder(self.sink, **{**self.context, **context})

    def emit(self, kind, **data):
        self.sink.append({"kind": kind, **self.context, **data})

    __call__ = emit


@pytest.fixture
def listener():
    url = os.environ.get("TALNEX_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("TALNEX_TEST_DATABASE_URL is not set")
    conn = psycopg.connect(url, autocommit=True)
    conn.execute(f"LISTEN {live.CHANNEL}")

    def received(limit=50):
        return [json.loads(n.payload) for n in conn.notifies(timeout=0.5, stop_after=limit)]

    yield received
    conn.close()


def test_events_arrive_on_the_live_channel(pool, listener):
    subject = str(uuid.uuid4())
    Emitter(pool, "project", subject, job_id=None, stage="live_test").child(claim_id="c1").emit("reason", text="hi")
    [event] = [e for e in listener() if e["subject"]["id"] == subject]
    assert (event["v"], event["kind"], event["stage"], event["claim_id"], event["data"]) == (1, "reason", "live_test", "c1", {"text": "hi"})
    assert "job_id" not in event and event["at"].endswith("Z")


def test_big_events_are_cut_to_fit_and_still_arrive(pool, listener):
    subject = str(uuid.uuid4())
    Emitter(pool, "project", subject).emit("step.record", label="x" * 5000, items=["y" * 400] * 40)
    [event] = [e for e in listener() if e["subject"]["id"] == subject]
    assert len(event["data"]["label"]) == live.MAX_TEXT and event["data"]["label"].endswith("...")
    assert event["data"]["cut"] == ["items"] and "items" not in event["data"]  # the big field went, the label stayed
    assert len(live.encode({"data": {f"k{i}": "z" * 490 for i in range(40)}}).encode()) <= live.MAX_PAYLOAD


def test_sending_never_raises():
    class BrokenPool:
        def connection(self):
            raise psycopg.OperationalError("database went away")

    Emitter(BrokenPool(), "project", "p1").emit("reason", text="still fine")
    NullEmitter().child(claim_id="x").emit("anything")


def test_events_are_saved_for_replay_once_the_table_exists(pool):
    with pool.connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS live_events (id bigserial PRIMARY KEY, subject_kind text NOT NULL,
                        subject_id uuid NOT NULL, job_id uuid, kind text NOT NULL, payload jsonb NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now())""")
    live._table_seen.clear()
    subject = str(uuid.uuid4())
    try:
        Emitter(pool, "project", subject).emit("verdict", verdict="works")
        with pool.connection() as conn:
            rows = conn.execute("SELECT kind, payload FROM live_events WHERE subject_id = %s", (subject,)).fetchall()
        assert rows[0][0] == "verdict" and rows[0][1]["data"] == {"verdict": "works"}
    finally:
        with pool.connection() as conn:
            conn.execute("DROP TABLE live_events")
        live._table_seen.clear()


def test_the_test_loop_streams_reasons_actions_results_and_the_outcome():
    events = Recorder()
    model = ScriptedModel({"thought": "typing the first todo", "action": {"type": "press", "key": "Enter"}},
                          done("listed"), verdict())
    execute_plan(model, FakeDriver(), PLAN, claim_text="Add todos", site_url="https://demo.example.com/",
                 cfg=ExecConfig(), uploads_root=Path("."), save_proof=lambda n, b: f"s/{n}", on_event=events)
    kinds = [e["kind"] for e in events.sink]
    assert kinds == ["reason", "step.record", "reason", "step.result", "step.record", "run.outcome"]
    assert events.sink[0]["text"] == "typing the first todo"
    assert events.sink[1]["label"] == "Press Enter" and events.sink[1]["proof_key"] == "s/1"
    assert events.sink[-1]["outcome"] == "works"


def test_a_broken_listener_never_stops_the_test():
    def explode(kind, **data):
        raise RuntimeError("live view down")

    result = execute_plan(ScriptedModel(done(), verdict()), FakeDriver(), PLAN, claim_text="x",
                          site_url="https://demo.example.com/", cfg=ExecConfig(), uploads_root=Path("."),
                          save_proof=lambda n, b: None, on_event=explode)
    assert result.outcome == "works"


def test_every_job_streams_its_stage_start_and_end(pool, listener):
    target = str(uuid.uuid4())
    queue.enqueue_job(pool, "echo", "python", "project", target)
    job = queue.take_job(pool, "python", "w")
    Worker(pool, "", {"echo": lambda job, ctx: {"skipped": True, "reason": "nothing to do"}}, worker_id="w").run_one("w", job)
    mine = [e for e in listener() if e["subject"]["id"] == target]
    assert [e["kind"] for e in mine] == ["stage.started", "stage.finished"]
    assert mine[1]["stage"] == "echo" and mine[1]["data"]["skipped"] and mine[1]["data"]["reason"] == "nothing to do"

    queue.enqueue_job(pool, "boom", "python", "project", target)
    job = queue.take_job(pool, "python", "w")
    Worker(pool, "", {"boom": lambda job, ctx: 1 / 0}, worker_id="w").run_one("w", job)
    failed = [e for e in listener() if e["subject"]["id"] == target]
    assert failed[-1]["kind"] == "stage.failed" and failed[-1]["data"]["status"] == "retrying"
    assert "ZeroDivisionError" in failed[-1]["data"]["error"]


def test_for_job_needs_a_known_target():
    job = SimpleNamespace(target_type="robot", target_id="x", id="j", type="t", pipeline=None, run_number=1)
    assert isinstance(for_job(object(), job), NullEmitter)


ENV = {"DATABASE_URL": "postgres://x", "S3_ENDPOINT": "http://s3:9000", "S3_REGION": "auto", "S3_BUCKET": "b",
       "S3_ACCESS_KEY": "a", "S3_SECRET_KEY": "s", "OPENROUTER_BASE_URL": "https://or.test",
       "TINYFISH_AGENT_BASE_URL": "https://a.test", "TINYFISH_BROWSER_BASE_URL": "https://b.test",
       "TINYFISH_FETCH_BASE_URL": "https://f.test", "AGENTMAIL_BASE_URL": "https://m.test"}


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event = conn.execute("""INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
                                VALUES (%s, 'pytest event', 'open_theme', now() - interval '1 day', now()) RETURNING id""",
                             (user,)).fetchone()[0]
        project_id = conn.execute("INSERT INTO projects (event_id, team_name, live_url) VALUES (%s, 'T', %s) RETURNING id::text",
                                  (event, "https://demo.example.com/")).fetchone()[0]
        claim_id = conn.execute("""INSERT INTO claims (project_id, text, claim_group, importance, source)
                                   VALUES (%s, 'Add todos', 'Core', 2, 'video') RETURNING id::text""", (project_id,)).fetchone()[0]
    yield SubjectInfo(Subject("project", project_id), "T", "https://demo.example.com/", None, None, "fresher"), \
        Claim(id=claim_id, text="Add todos", claim_group="Core", importance=2, source="video")
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_a_whole_claim_streams_from_start_to_verdict(pool, project):
    info, claim = project
    events = Recorder()
    model = ScriptedModel(act(type="press", key="Enter"), done("listed"), verdict(),
                          {"outcome": "works", "seen": "The todo is listed."})
    sv = SimpleNamespace(pool=pool, cfg=settings.load(ENV), model=model, tinyfish=FakeTinyFish(), files=FakeFiles(),
                         connect=connector(FakeDriver()), uploads_root=Path("."), mailbox_for=lambda h: None, smsbox_for=None)
    since = datetime.now(timezone.utc) - timedelta(minutes=5)
    live_test_subject(sv, info, [claim], {}, {"claims": {claim.id: {"plans": [PLAN.model_dump()]}}}, since, "job-1",
                      events=events)
    kinds = [e["kind"] for e in events.sink]
    assert kinds[:3] == ["claims.queued", "claim.started", "ladder"]
    for expected in ("run.started", "reason", "step.record", "run.outcome", "run.finished", "check.started", "check"):
        assert expected in kinds
    assert kinds[-1] == "verdict" and events.sink[-1]["verdict"] == "works" and events.sink[-1]["claim_id"] == claim.id
    run_events = [e for e in events.sink if e["kind"].startswith("run.") or e["kind"] == "step.record"]
    assert all(e.get("run_id") for e in run_events)  # every browser event says which run it belongs to


def test_the_terminal_view_reads_well():
    line = describe({"kind": "verdict", "at": "2026-10-24T14:03:41.120Z", "stage": "live_test",
                     "data": {"verdict": "works", "confidence": "high", "reason": "seen"}})
    assert line.startswith("14:03:41") and "VERDICT works (high): seen" in line
    assert "unknown.kind" in describe({"kind": "unknown.kind", "data": {"a": 1}})
