"""Cloning a repo into a VM, working out how to run it, building and starting it. A scripted fake VM stands in for the real one."""
import json
import re
import uuid
from types import SimpleNamespace

import pytest

from talnex_ai.claims.store import Subject
from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.client import ExecResult, HttpResult, SandboxUnavailable
from talnex_ai.sandbox.stack_detect import prepare_and_run
from talnex_ai.sandbox.stack_detect.bringup import bring_up
from talnex_ai.sandbox.stack_detect.detect import RepoFacts
from talnex_ai.sandbox.stack_detect.fix import RecipeFix, apply_fix
from talnex_ai.sandbox.stack_detect.gather import clean_github_url, parse_file_dump, paths_to_read
from talnex_ai.sandbox.stack_detect.recipe import Recipe
from talnex_ai.sandbox.store import latest_run
from talnex_ai.settings import SandboxSettings
from talnex_ai.worker.handlers import sandbox_run as stage_module
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services

EXPRESS_PKG = json.dumps({"scripts": {"start": "node index.js"}, "dependencies": {"express": "4"}})
NODE_REPO = {"package.json": EXPRESS_PKG, "index.js": "x", "README.md": "# App"}
LOCKED_NODE_REPO = {**NODE_REPO, "package-lock.json": "{}"}
PY_REPO = {"requirements.txt": "fastapi\nuvicorn\n", "main.py": "from fastapi import FastAPI\napp = FastAPI()\n"}


class FakeVm:
    """A pretend VM holding a pretend repo. `fail` maps a piece of a command to the result it should give."""

    def __init__(self, image, repo=None, fail=None, listens=True, private=False, services=()):
        self.id, self.image = str(uuid.uuid4()), image
        self.repo, self.fail, self.listens, self.private = repo or {}, fail or {}, listens, private
        self.services = list(services)
        self.commands: list[str] = []
        self.started = False
        self.destroyed = False

    def exec(self, command, **kw):
        self.commands.append(command)
        for piece, result in self.fail.items():
            if piece in command:
                return result
        if "git clone" in command:
            if self.private:
                return ExecResult(128, stderr="fatal: could not read Username for 'https://github.com': terminal prompts disabled")
            return ExecResult(0)
        if "git ls-files" in command:
            return ExecResult(0, stdout="\n".join(self.repo))
        if "@@@TALNEX-FILE" in command:
            paths = re.findall(r'@@@TALNEX-FILE ([^"]+)"', command)
            return ExecResult(0, stdout="\n".join(f"@@@TALNEX-FILE {p}\n{self.repo.get(p, '')}\n" for p in paths))
        if kw.get("detach"):
            self.started = True
            return ExecResult(0)
        if "tail -n" in command:
            return ExecResult(0, stdout="Server listening" if self.started else "")
        return ExecResult(0, stdout="ok")

    def wait_for_port(self, *, timeout_seconds=60, port=None, poll_seconds=1.0):
        return (port or 3000) if (self.started and self.listens) else None

    def request(self, method, port, path, **kw):
        return HttpResult(status=200 if self.started else 0, body=b"hi")

    def destroy(self):
        self.destroyed = True


class Factory:
    """Makes the VMs, remembers them, and gives each the repo it should hold."""

    def __init__(self, repo, **vm_kw):
        self.repo, self.vm_kw, self.made = repo, vm_kw, []

    def __call__(self, image, services=()):
        vm = FakeVm(image, self.repo, services=services, **self.vm_kw)
        self.made.append(vm)
        return vm


class ScriptedModel:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, role, messages, **kw):
        self.calls += 1
        text = self.replies.pop(0)
        return SimpleNamespace(text=text if isinstance(text, str) else json.dumps(text))


URL = "https://github.com/team/app"


# ------------------------------------------------------------------ small helpers


@pytest.mark.parametrize("raw,want", [
    ("https://github.com/a/b", "https://github.com/a/b"),
    ("github.com/a/b.git", "https://github.com/a/b"),
    ("https://www.github.com/a/b/tree/main/x", "https://github.com/a/b"),
    ("http://github.com/a/b/", "https://github.com/a/b"),
    ("https://gitlab.com/a/b", None), ("https://github.com/a", None), ("", None),
    ("https://github.com/a/b; rm -rf /", None) if False else ("https://evil.com/github.com/a/b", None),
])
def test_clean_github_url(raw, want):
    assert clean_github_url(raw) == want


def test_a_dump_of_files_is_split_back_into_files():
    dump = "@@@TALNEX-FILE a.txt\nline1\nline2\n\n@@@TALNEX-FILE sub/b.json\n{}\n"
    assert parse_file_dump(dump) == {"a.txt": "line1\nline2", "sub/b.json": "{}"}


def test_only_the_files_that_decide_how_it_runs_are_read_and_odd_names_are_skipped():
    files = ["package.json", "README.md", "src/big.js", "server/package.json", "weird name.json", "$(x)/package.json", "Dockerfile"]
    got = paths_to_read(files)
    assert "package.json" in got and "server/package.json" in got and "README.md" in got and "Dockerfile" in got
    assert not any(" " in p or "$" in p or p == "src/big.js" for p in got)


# ------------------------------------------------------------------ bring up


def node_recipe(**kw):
    return Recipe(stack="node", image="talnex-sandbox-full", install_cmd="npm ci", start_cmd="npm start", **kw)


def test_a_healthy_app_is_running_with_its_port_and_a_health_path():
    vm = FakeVm("i")
    out = bring_up(vm, node_recipe())
    assert out.ok and out.port == 3000 and out.health_path == "/" and out.health_status == 200
    assert [s.name for s in out.steps] == ["install", "start"]


def test_a_failed_install_stops_before_starting_and_keeps_the_end_of_the_output():
    vm = FakeVm("i", fail={"npm ci": ExecResult(1, stderr="npm ERR! 404 not found: left-padz")})
    out = bring_up(vm, node_recipe())
    assert not out.ok and out.failed_step == "install" and "left-padz" in out.steps[0].output_tail and not vm.started


def test_an_app_that_never_listens_is_a_start_failure():
    out = bring_up(FakeVm("i", listens=False), node_recipe())
    assert not out.ok and out.failed_step == "start" and "did not start listening" in out.reason


def test_an_app_that_only_answers_with_server_errors_is_not_healthy_but_a_404_is():
    class V(FakeVm):
        status = 500

        def request(self, method, port, path, **kw):
            return HttpResult(status=self.status)

    sick = V("i")
    assert bring_up(sick, node_recipe()).failed_step == "health"
    well = V("i")
    well.status = 404
    assert bring_up(well, node_recipe()).ok


def test_a_recipe_with_no_start_command_does_not_pretend():
    out = bring_up(FakeVm("i"), Recipe(stack="node", image="x"))
    assert not out.ok and out.failed_step == "start"


# ------------------------------------------------------------------ the whole run


def test_a_node_repo_comes_up_and_the_vm_is_kept_for_the_next_stages():
    factory = Factory(NODE_REPO)
    res = prepare_and_run(factory, None, URL)
    assert res.ok and res.vm is factory.made[0] and not res.vm.destroyed and res.recipe.stack == "node"
    assert len(factory.made) == 1 and not res.fix_used


def test_a_python_repo_runs_in_the_same_single_vm():
    factory = Factory(PY_REPO)
    res = prepare_and_run(factory, None, URL)
    assert [v.image for v in factory.made] == ["talnex-sandbox-full"] and res.ok and res.vm is factory.made[0]
    assert not res.vm.destroyed


def test_a_stack_with_its_own_image_replaces_the_first_vm(monkeypatch):
    from talnex_ai.sandbox.stack_detect import recipe as recipe_module

    monkeypatch.setitem(recipe_module.IMAGES, "python", "talnex-sandbox-pyspecial")
    factory = Factory(PY_REPO)
    res = prepare_and_run(factory, None, URL)
    assert [v.image for v in factory.made] == ["talnex-sandbox-full", "talnex-sandbox-pyspecial"]
    assert factory.made[0].destroyed and res.ok and res.vm is factory.made[1]
    assert any("git clone" in c for c in factory.made[1].commands)


def test_a_private_or_missing_repo_is_not_reachable_and_nothing_is_left_running():
    factory = Factory({}, private=True)
    res = prepare_and_run(factory, None, URL)
    assert res.status == "could_not_run" and "repo not reachable" in res.reason and all(v.destroyed for v in factory.made)


def test_a_link_that_is_not_github_is_refused_before_any_vm_is_made():
    factory = Factory(NODE_REPO)
    res = prepare_and_run(factory, None, "https://gitlab.com/a/b")
    assert res.status == "could_not_run" and "not a GitHub address" in res.reason and factory.made == []


def test_a_stack_with_no_image_yet_is_could_not_run_with_the_reason():
    factory = Factory({"go.mod": "module x", "main.go": "package main"})
    res = prepare_and_run(factory, None, URL)
    assert res.status == "could_not_run" and "no Go image" in res.reason and res.vm is factory.made[0] and not res.vm.destroyed  # kept for the code review


def test_a_failed_install_gets_exactly_one_model_fix_and_then_runs():
    factory = Factory(LOCKED_NODE_REPO, fail={"npm ci": ExecResult(1, stderr="npm ERR! peer dependency conflict")})
    model = ScriptedModel({"install_cmd": "npm install --legacy-peer-deps", "explanation": "peer dependency conflict"})
    # the changed install command no longer matches "npm ci", so the second try goes through
    res = prepare_and_run(factory, model, URL)
    assert res.ok and res.fix_used and model.calls == 1
    assert res.recipe.source == "model_fix" and "peer dependency" in res.recipe.notes[-1]
    assert [len(a.steps) for a in res.attempts] == [1, 2]


def test_when_the_fix_does_not_help_it_is_could_not_run_and_the_model_is_asked_only_once():
    factory = Factory(NODE_REPO, fail={"npm": ExecResult(1, stderr="npm ERR! boom")})
    model = ScriptedModel({"install_cmd": "npm install --force"})
    res = prepare_and_run(factory, model, URL)
    assert res.status == "could_not_run" and model.calls == 1 and len(res.attempts) == 2
    assert "one automatic fix" in res.reason and "install step failed" in res.reason and res.vm is factory.made[-1] and not res.vm.destroyed


def test_a_model_that_changes_nothing_or_answers_badly_leaves_the_first_failure_standing():
    factory = Factory(LOCKED_NODE_REPO, fail={"npm ci": ExecResult(1, stderr="x")})
    same = ScriptedModel({"install_cmd": "npm ci --no-audit --no-fund || npm install --no-audit --no-fund", "explanation": "nothing"})
    res = prepare_and_run(factory, same, URL)
    assert res.status == "could_not_run" and not res.fix_used and len(res.attempts) == 1

    garbage = ScriptedModel("not json", "still not json")
    res = prepare_and_run(Factory(LOCKED_NODE_REPO, fail={"npm ci": ExecResult(1, stderr="x")}), garbage, URL)
    assert res.status == "could_not_run" and not res.fix_used


def test_a_repo_that_needs_a_database_gets_one_started_beside_it_with_real_settings():
    pkg = json.dumps({"scripts": {"start": "node a.js"}, "dependencies": {"express": "4", "mongoose": "8"}})
    factory = Factory({"package.json": pkg, "a.js": "x"}, listens=True)
    res = prepare_and_run(factory, None, URL)
    assert res.status == "running"
    # the VM that ran the app was created with the mongo service and given its real connection settings, not a fake
    app_vm = factory.made[-1]
    assert app_vm.services == ["mongodb"]
    assert res.recipe.env.get("MONGO_URL") == "mongodb://mongodb:27017"


def test_a_repo_that_needs_a_service_but_still_will_not_start_is_an_honest_could_not_run():
    pkg = json.dumps({"scripts": {"start": "node a.js"}, "dependencies": {"express": "4", "pg": "8"}})
    factory = Factory({"package.json": pkg, "a.js": "x"}, listens=False)
    res = prepare_and_run(factory, None, URL)
    assert res.status == "could_not_run" and factory.made[-1].services == ["postgres"]


def test_a_fix_may_only_name_folders_that_exist_in_the_repo():
    recipe = node_recipe()
    facts = RepoFacts(files=["server/index.js", "package.json"])
    assert apply_fix(recipe, RecipeFix(app_dir="server"), facts).app_dir == "server"
    assert apply_fix(recipe, RecipeFix(app_dir="nope"), facts) is None
    assert apply_fix(recipe, RecipeFix(app_dir="../etc"), facts) is None
    assert apply_fix(recipe, RecipeFix(explanation="cannot tell"), facts) is None


# ------------------------------------------------------------------ the stage


class FakeFiles:
    def __init__(self):
        self.put = {}

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        self.put[key] = data


class FakeSandboxClient:
    def __init__(self, repo, **vm_kw):
        self.factory, self.destroyed = Factory(repo, **vm_kw), []

    def open_vm(self, image, services=()):
        return self.factory(image, services=services)

    def destroy(self, vm_id):
        self.destroyed.append(vm_id)


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id",
                           (uid,)).fetchone()[0]
        return conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s, 'T', %s) RETURNING id::text", (eid, URL)).fetchone()[0]


def run_stage(pool, project_id, client, enabled=True, model=None, files=None):
    cfg = SimpleNamespace(sandbox=SandboxSettings("http://x" if enabled else "", "t" if enabled else "", 900, 600, 20))
    set_services(Services(cfg, pool, model, None, files or FakeFiles(), lambda host: None, None, sandbox=client))
    job = Job(str(uuid.uuid4()), "sandbox_run", "python", "project", project_id, {}, "hackathon", 1, 1, 3, 60)
    try:
        return stage_module.sandbox_run(job, JobContext(job, pool))
    finally:
        set_services(None)


class TestSandboxRunStage:
    def test_a_running_app_is_recorded_with_its_vm_port_and_logs(self, pool, project):
        client, files = FakeSandboxClient(NODE_REPO), FakeFiles()
        out = run_stage(pool, project, client, files=files)
        assert out["status"] == "running" and out["port"] == 3000
        run = latest_run(pool, Subject("project", project))
        assert run.status == "running" and run.vm_id == client.factory.made[0].id and run.port == 3000
        assert run.recipe["stack"] == "node" and run.image == "talnex-sandbox-full"
        assert run.build_log_key in files.put and b"npm install" in files.put[run.build_log_key]

    def test_a_repo_that_cannot_run_is_recorded_with_the_reason_and_its_vm_kept_only_for_the_code_review(self, pool, project):
        client = FakeSandboxClient({"go.mod": "x", "main.go": "x"})
        out = run_stage(pool, project, client)
        run = latest_run(pool, Subject("project", project))
        assert out["status"] == "could_not_run" and run.status == "could_not_run" and "no Go image" in run.status_detail
        vm = client.factory.made[-1]
        assert not vm.destroyed and run.vm_id == vm.id and run.code_readable and not run.port

    def test_a_host_that_is_not_set_up_is_could_not_run_not_a_failure(self, pool, project):
        out = run_stage(pool, project, None, enabled=False)
        run = latest_run(pool, Subject("project", project))
        assert out["status"] == "could_not_run" and "not set up" in out["reason"] and run.status == "could_not_run"

    def test_a_host_that_fails_makes_the_stage_fail_so_the_queue_tries_again_and_the_project_is_not_blamed(self, pool, project):
        class Down(FakeSandboxClient):
            def open_vm(self, image, services=()):
                raise SandboxUnavailable("the sandbox host did not answer")

        with pytest.raises(SandboxUnavailable):
            run_stage(pool, project, Down({}))
        assert latest_run(pool, Subject("project", project)).status == "could_not_run"

    def test_no_repository_means_the_stage_is_skipped(self, pool, project):
        with pool.connection() as conn:
            conn.execute("UPDATE projects SET repo_url = NULL WHERE id = %s::uuid", (project,))
        assert run_stage(pool, project, FakeSandboxClient({}))["skipped"]

    def test_running_the_stage_again_destroys_the_earlier_vm(self, pool, project):
        client = FakeSandboxClient(NODE_REPO)
        run_stage(pool, project, client)
        first_vm = client.factory.made[0].id
        run_stage(pool, project, client)
        assert first_vm in client.destroyed
        assert latest_run(pool, Subject("project", project)).vm_id == client.factory.made[-1].id


def test_an_app_that_listens_but_answers_only_500_is_still_kept_running_for_the_test_stages(monkeypatch):
    monkeypatch.setattr(FakeVm, "request", lambda self, method, port, path, **kw: HttpResult(status=500), raising=False)
    factory = Factory(NODE_REPO)
    res = prepare_and_run(factory, None, URL)
    assert res.status == "running" and res.vm is factory.made[0] and not res.vm.destroyed
    assert res.bringup.failed_step == "health" and res.bringup.port


def test_settings_the_code_reads_get_a_temporary_fake_env_but_set_values_are_kept():
    from talnex_ai.sandbox.stack_detect.envvalues import code_env_names

    code = 'const k = process.env.STRIPE_SECRET_KEY; db(process.env["MONGO_URI"]); x = os.getenv("JWT_EXPIRES_IN"); os.environ["HOME"]'
    assert code_env_names(code) == ["STRIPE_SECRET_KEY", "MONGO_URI", "JWT_EXPIRES_IN"]

    class Greps(FakeVm):
        def exec(self, command, **kw):
            if command.startswith("grep -rhoE"):
                return ExecResult(0, stdout="process.env.STRIPE_SECRET_KEY\nprocess.env.PORT\n")
            return super().exec(command, **kw)

    made = []
    res = prepare_and_run(lambda image, services=(): made.append(Greps(image, NODE_REPO)) or made[-1], None, URL)
    assert res.ok and res.recipe.env["STRIPE_SECRET_KEY"].startswith("talnex-placeholder") and res.recipe.env["PORT"] == "3000"
