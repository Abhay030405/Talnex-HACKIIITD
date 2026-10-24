"""The repository's own tests, run inside the VM: reading the counts and judging them as evidence."""
import uuid
from types import SimpleNamespace

import pytest

from talnex_ai.claims.store import Subject, load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.client import ExecResult, SandboxError
from talnex_ai.sandbox.repo_tests import TestCounts, describe, parse_test_output
from talnex_ai.sandbox.store import create_run, update_run
from talnex_ai.settings import SandboxSettings
from talnex_ai.worker.handlers import repo_tests as stage_module
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services


@pytest.mark.parametrize("text,want", [
    ("collected 12 items\n=========== 2 failed, 10 passed, 1 skipped in 3.20s ===========", (10, 2, "pytest")),
    ("10 passed in 1.02s", (10, 0, "pytest")),
    ("Tests:       1 failed, 4 passed, 5 total\nTime: 2s", (4, 1, "jest")),
    ("Tests:       4 passed, 4 total", (4, 0, "jest")),
    (" Test Files  1 passed (1)\n      Tests  2 failed | 6 passed (8)", (6, 2, "vitest")),
    ("  5 passing (20ms)\n  2 failing", (5, 2, "mocha")),
    ("# tests 4\n# pass 3\n# fail 1", (3, 1, "node:test")),
    ("Ran 7 tests in 0.1s\n\nOK", (7, 0, "unittest")),
    ("Ran 7 tests in 0.1s\n\nFAILED (failures=2, errors=1)", (4, 3, "unittest")),
])
def test_counts_are_read_from_each_frameworks_summary(text, want):
    got = parse_test_output(text)
    assert (got.passed, got.failed, got.framework) == want


def test_text_with_no_summary_gives_no_counts():
    assert parse_test_output("npm ERR! missing script: test") is None and parse_test_output("") is None


class TestDescribe:
    def test_all_passing_works(self):
        assert describe(TestCounts(8, 0, "jest"), 0, False)[0] == "works"

    def test_some_passing_is_partly_working_with_the_numbers(self):
        verdict, reason = describe(TestCounts(4, 1, "jest"), 1, False)
        assert verdict == "partly_works" and "4 of 5" in reason

    def test_none_passing_is_could_not_confirm_not_broken(self):
        verdict, reason = describe(TestCounts(0, 6, "pytest"), 1, False)
        assert verdict == "could_not_test" and "database or keys" in reason

    def test_no_counts_depends_on_the_exit_code_and_a_timeout_is_never_a_verdict(self):
        assert describe(None, 0, False)[0] == "works" and describe(None, 2, False)[0] == "could_not_test"
        assert describe(TestCounts(5, 0, "jest"), 0, True)[0] == "could_not_test"


class FakeVm:
    def __init__(self, result):
        self.result, self.commands = result, []

    def exec(self, command, **kw):
        self.commands.append((command, kw))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Client:
    def __init__(self, vm):
        self.vm = vm

    def attach(self, vm_id):
        return self.vm


class Files:
    def __init__(self):
        self.put = {}

    def put_bytes(self, key, data, content_type=""):
        self.put[key] = data


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id",
                           (uid,)).fetchone()[0]
        return conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s, 'T', 'https://github.com/a/b') RETURNING id::text", (eid,)).fetchone()[0]


def start(pool, project, test_cmd="npm test"):
    run_id = create_run(pool, Subject("project", project))
    update_run(pool, run_id, status="running", recipe={"test_cmd": test_cmd, "env": {"CI": "1"}}, resources={"vm_id": "vm1", "port": 3000, "app_dir": "server"})


def call(pool, project, vm, files=None):
    cfg = SimpleNamespace(sandbox=SandboxSettings("http://x", "t", 900, 600, 20))
    set_services(Services(cfg, pool, None, None, files or Files(), lambda host: None, None, sandbox=Client(vm)))
    job = Job(str(uuid.uuid4()), "repo_tests", "python", "project", project, {}, "sandbox_check_project", 1, 1, 3, 3000)
    try:
        return stage_module.repo_tests(job, JobContext(job, pool))
    finally:
        set_services(None)


def result_of(pool, project):
    claim = next(c for c in load_claims(pool, Subject("project", project)) if c.text == stage_module.CLAIM_TEXT)
    with pool.connection() as conn:
        return claim, conn.execute("SELECT verdict, confidence, reason, proof_keys FROM results WHERE claim_id = %s::uuid", (claim.id,)).fetchone()


class TestRepoTestsStage:
    def test_a_run_is_saved_with_its_verdict_proof_and_a_command_step(self, pool, project):
        start(pool, project)
        files = Files()
        vm = FakeVm(ExecResult(1, stdout="Tests:       1 failed, 4 passed, 5 total"))
        out = call(pool, project, vm, files)
        claim, (verdict, confidence, reason, proofs) = result_of(pool, project)
        assert out["verdict"] == "partly_works" and (out["passed"], out["failed"]) == (4, 1)
        assert verdict == "partly_works" and "4 of 5" in reason and proofs and proofs[0] in files.put
        assert claim.claim_group == "Reliability" and claim.importance == 1 and claim.track == "sandbox"
        command, kw = vm.commands[0]
        assert command == "npm test" and kw["workdir"] == "/work/repo/server" and kw["env"] == {"CI": "1"}
        with pool.connection() as conn:
            row = conn.execute("SELECT t.track, t.test_type, t.method, s.kind FROM test_runs t JOIN steps s ON s.run_id = t.id WHERE t.claim_id = %s::uuid", (claim.id,)).fetchone()
        assert row == ("sandbox", "repo_tests", "command", "command")

    def test_pytest_is_made_sure_of_first(self, pool, project):
        start(pool, project, "python -m pytest -x -q")
        vm = FakeVm(ExecResult(0, stdout="3 passed in 0.1s"))
        call(pool, project, vm)
        assert vm.commands[0][0].startswith("python -m pip install -q pytest") and vm.commands[0][0].endswith("python -m pytest -x -q")

    def test_no_test_command_means_no_claim_and_a_skip(self, pool, project):
        start(pool, project, "")
        out = call(pool, project, FakeVm(ExecResult(0)))
        assert out["skipped"] and not any(c.text == stage_module.CLAIM_TEXT for c in load_claims(pool, Subject("project", project)))

    def test_a_sandbox_failure_is_could_not_test_and_not_a_verdict_on_the_repo(self, pool, project):
        start(pool, project)
        out = call(pool, project, FakeVm(SandboxError("the host did not answer")))
        assert out["skipped"] and result_of(pool, project)[1][0] == "could_not_test"

    def test_nothing_running_is_skipped(self, pool, project):
        assert call(pool, project, FakeVm(ExecResult(0)))["skipped"]
