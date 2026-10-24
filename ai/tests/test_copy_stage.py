"""The event-level copy stage: pairs saved, flags on both teams (never a score), a model look can only soften a flag, a team that
cannot be read is left out, a re-run replaces the old flags, and the last team to finish starts the event checks."""
import json
import uuid
from types import SimpleNamespace

import pytest

from talnex_ai.checks.copy_between_teams import PairLook, fingerprint as fp
from talnex_ai.db.jobs import Job
from talnex_ai.settings import CopySettings, SandboxSettings
from talnex_ai.worker.handlers import copy_between_teams as stage_module
from talnex_ai.worker.handlers.project_report import start_event_checks
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services
from tests.test_copy_between_teams import OTHER, RENAMED, TODOS


class Vm:
    destroyed = 0

    def destroy(self):
        Vm.destroyed += 1


class Sandbox:
    def open_vm(self, image):
        return Vm()


@pytest.fixture
def event(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id::text",
                           (uid,)).fetchone()[0]
        ids = {name: conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s::uuid, %s, %s) RETURNING id::text",
                                  (eid, name, f"https://github.com/x/{name.lower()}")).fetchone()[0] for name in ("Alpha", "Beta", "Gamma")}
    return eid, ids


def run_stage(pool, eid, monkeypatch, codes, look=None):
    prints = {f"https://github.com/x/{n.lower()}": ({p: fp.fingerprint_text(t, ".js") for p, t in files.items()} if files else None) for n, files in codes.items()}

    def fake_fingerprint(vm, url):
        if prints.get(url) is None:
            raise stage_module.RepoUnreachable("the repository could not be cloned")
        return prints[url]

    monkeypatch.setattr(stage_module, "fingerprint_repo", fake_fingerprint)
    monkeypatch.setattr(stage_module, "_look", lambda sv, job, a, b, pair: look)
    cfg = SimpleNamespace(sandbox=SandboxSettings("http://x", "t", 900, 600, 20), copy=CopySettings())
    set_services(Services(cfg, pool, None, None, None, lambda host: None, None, sandbox=Sandbox()))
    job = Job(str(uuid.uuid4()), "copy_between_teams", "python", "event", eid, {}, "hackathon_event", 1, 1, 3, 3600)
    try:
        return stage_module.copy_between_teams(job, JobContext(job, pool))
    finally:
        set_services(None)


def flags_of(pool, pid):
    with pool.connection() as conn:
        return conn.execute("SELECT level, evidence->>'other_team' FROM flags WHERE project_id = %s::uuid AND flag_type = 'copied_from_team'", (pid,)).fetchall()


CODES = {"Alpha": {"todo.js": TODOS}, "Beta": {"tasks.js": RENAMED}, "Gamma": {"weather.js": OTHER}}


def test_a_renamed_copy_flags_both_teams_and_the_unrelated_team_stays_clean(pool, event, monkeypatch):
    eid, ids = event
    out = run_stage(pool, eid, monkeypatch, CODES)
    assert out["teams_compared"] == 3 and out["flagged_teams"] == 2
    assert flags_of(pool, ids["Alpha"])[0][1] == "Beta" and flags_of(pool, ids["Beta"])[0][1] == "Alpha" and flags_of(pool, ids["Gamma"]) == []
    with pool.connection() as conn:
        rows = conn.execute("SELECT count(*), max(shared_pct) FROM copy_pairs WHERE event_id = %s::uuid", (eid,)).fetchone()
    assert rows[0] == 3 and float(rows[1]) > 70


def test_the_model_can_only_soften_a_flag(pool, event, monkeypatch):
    eid, ids = event
    run_stage(pool, eid, monkeypatch, CODES, look=PairLook(verdict="starter_or_library", reason="a template"))
    assert flags_of(pool, ids["Alpha"])[0][0] == "review"          # strong -> review
    run_stage(pool, eid, monkeypatch, CODES, look=PairLook(verdict="copied", reason="same unusual steps"))
    assert [lvl for lvl, _ in flags_of(pool, ids["Alpha"])] == ["strong"]     # a re-run replaced the old flag, and "copied" keeps it


def test_a_team_that_cannot_be_read_is_left_out_not_marked(pool, event, monkeypatch):
    eid, ids = event
    out = run_stage(pool, eid, monkeypatch, {"Alpha": {"todo.js": TODOS}, "Beta": {"tasks.js": RENAMED}, "Gamma": None})
    assert out["could_not_read"] == {"Gamma": "the repository could not be cloned"} and flags_of(pool, ids["Gamma"]) == []


def test_fewer_than_two_repositories_is_skipped(pool, event, monkeypatch):
    eid, ids = event
    with pool.connection() as conn:
        conn.execute("UPDATE projects SET repo_url = NULL WHERE event_id = %s::uuid AND team_name <> 'Alpha'", (eid,))
    assert run_stage(pool, eid, monkeypatch, CODES)["skipped"]


def test_the_proof_card_is_rebuilt_so_it_shows_the_flag(pool, event, monkeypatch):
    eid, ids = event
    saved = []
    monkeypatch.setattr(stage_module, "save_card", lambda p, pid: saved.append(pid))
    run_stage(pool, eid, monkeypatch, CODES)
    assert sorted(saved) == sorted([ids["Alpha"], ids["Beta"]])


def test_the_last_team_to_finish_starts_the_event_checks_once(pool, event):
    eid, ids = event
    def report_job(pid, status):
        with pool.connection() as conn:
            conn.execute("INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, status, time_limit_seconds, max_tries, dedupe_key) "
                         "VALUES ('project_report', 'python', 'project', %s::uuid, 'hackathon', %s, 600, 3, %s)", (pid, status, f"pr:{pid}"))
    report_job(ids["Alpha"], "done")
    assert start_event_checks(pool, ids["Alpha"]) is False                 # two teams have not reached the report yet
    report_job(ids["Beta"], "done")
    report_job(ids["Gamma"], "running")
    assert start_event_checks(pool, ids["Gamma"]) is True
    assert start_event_checks(pool, ids["Beta"]) is False                  # the same run again adds nothing
    with pool.connection() as conn:
        n = conn.execute("SELECT count(*) FROM jobs WHERE pipeline = 'hackathon_event' AND target_id = %s::uuid", (eid,)).fetchone()[0]
    assert n == 1
