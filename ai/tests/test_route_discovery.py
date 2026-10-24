"""Route discovery: from a running backend and its repo to a list of routes linked to claims."""
import json
import re
import uuid
from types import SimpleNamespace

import pytest

from talnex_ai.claims.store import Subject, load_claims, save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim
from talnex_ai.sandbox.client import ExecResult, HttpResult, SandboxError
from talnex_ai.sandbox.route_discovery import Discovery, discover, from_json, source_files_for_routes, to_json
from talnex_ai.sandbox.stack_detect.detect import RepoFacts
from talnex_ai.sandbox.store import create_run, latest_run, update_run
from talnex_ai.settings import SandboxSettings
from talnex_ai.worker.handlers import route_discovery as stage_module
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services

SERVER = """const express = require('express');
const app = express();
app.get('/health', (q, r) => r.send('ok'));
app.post('/api/items', auth, create);
app.get('/api/items', list);
app.delete('/api/items/:id', auth, remove);
app.get('/api/stats', stats);
"""
FILES = {"server/index.js": SERVER, "server/package.json": "{}", "README.md": "# App\n`POST /api/login` signs in\n"}


class FakeVm:
    def __init__(self, files, spec=None):
        self.files, self.spec = files, spec

    def exec(self, command, **kw):
        paths = re.findall(r'@@@TALNEX-FILE ([^"]+)"', command)
        return ExecResult(0, stdout="\n".join(f"@@@TALNEX-FILE {p}\n{self.files.get(p, '')}\n" for p in paths))

    def request(self, method, port, path, **kw):
        if self.spec is not None and path == "/openapi.json":
            return HttpResult(200, body=json.dumps(self.spec).encode())
        return HttpResult(404)


class Model:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, role, messages, **kw):
        self.calls.append((role, messages[1]["content"]))
        text = self.replies.pop(0)
        return SimpleNamespace(text=text if isinstance(text, str) else json.dumps(text))


def claims(*texts):
    return [Claim(id=f"c{i}", text=t, claim_group="Core", importance=3, source="criteria") for i, t in enumerate(texts, start=1)]


def facts():
    return RepoFacts(files=list(FILES), texts={"README.md": FILES["README.md"]})


class TestSourceFiles:
    def test_route_looking_files_come_first_and_tests_and_libraries_are_left_out(self):
        files = ["server/index.js", "server/routes/users.js", "server/lib/util.js", "server/test/a.test.js", "server/node_modules/x/i.js",
                 "client/App.jsx", "server/models/user.js"]
        got = source_files_for_routes(files, "server")
        assert got[0] in ("server/index.js", "server/routes/users.js") and "client/App.jsx" not in got
        assert "server/test/a.test.js" not in got and "server/node_modules/x/i.js" not in got


class TestDiscover:
    def test_routes_come_from_the_code_and_the_readme_and_a_running_spec_wins(self):
        out = discover(FakeVm(FILES), None, port=3000, app_dir="server", facts=facts())
        assert {(r.method, r.path) for r in out.routes} == {
            ("GET", "/health"), ("POST", "/api/items"), ("GET", "/api/items"), ("DELETE", "/api/items/:id"), ("GET", "/api/stats"),
            ("POST", "/api/login")}
        spec = {"paths": {"/api/items": {"post": {"summary": "Create", "security": [{"b": []}]}}}}
        out = discover(FakeVm(FILES, spec=spec), None, port=3000, app_dir="server", facts=facts())
        post = next(r for r in out.routes if (r.method, r.path) == ("POST", "/api/items"))
        assert out.spec_found and post.source == "openapi" and post.needs_auth is True

    def test_without_a_model_every_route_except_plumbing_becomes_a_minor_claim(self):
        out = discover(FakeVm(FILES), None, port=3000, app_dir="server", facts=facts(), claims=claims("Add an item"))
        texts = [c.text for c in out.minor_claims]
        assert "The route GET /health exists and responds sensibly" not in texts
        assert "The route POST /api/items exists and responds sensibly" in texts
        assert all(c.source == "route" and c.track == "sandbox" and c.importance == 1 for c in out.minor_claims)
        assert len(out.minor_routes) == len(out.minor_claims)

    def test_the_model_links_claims_to_routes_and_adds_what_it_is_sure_of(self):
        out0 = discover(FakeVm(FILES), None, port=3000, app_dir="server", facts=facts())
        labels = [r.label() for r in out0.routes]
        add, lst = labels.index("POST /api/items") + 1, labels.index("GET /api/items") + 1
        model = Model({"links": [{"claim": 1, "routes": [add, lst]}, {"claim": 9, "routes": [1]}],
                       "routes": [{"route": add, "needs_auth": True, "body_fields": ["name"], "purpose": "create an item"}, {"route": 99}]})
        out = discover(FakeVm(FILES), model, port=3000, app_dir="server", facts=facts(), claims=claims("Add an item"))
        assert out.links == {"c1": sorted([add - 1, lst - 1])}   # the claim number 9 does not exist and is ignored
        created = out.routes[add - 1]
        assert created.needs_auth is True and created.body_fields == ["name"] and created.purpose == "create an item"
        served = {out.routes[i].label() for i in out.links["c1"]}
        assert not any(served & {c.text.split("route ")[1].split(" exists")[0] for c in out.minor_claims})
        assert model.calls[0][0] == "test_planner" and "Add an item" in model.calls[0][1]

    def test_a_model_that_answers_badly_is_not_fatal(self):
        model = Model("not json", "still not json")
        out = discover(FakeVm(FILES), model, port=3000, app_dir="server", facts=facts(), claims=claims("Add an item"))
        assert out.routes and out.links == {} and any("could not link" in n for n in out.notes)

    def test_no_routes_at_all_says_so_and_asks_nothing(self):
        model = Model()
        out = discover(FakeVm({"server/index.js": "console.log(1)"}), model, port=3000, app_dir="server",
                       facts=RepoFacts(files=["server/index.js"]), claims=claims("Do something"))
        assert out.routes == [] and out.notes and model.calls == []

    def test_a_discovery_survives_being_saved_as_plain_data(self):
        out = discover(FakeVm(FILES), None, port=3000, app_dir="server", facts=facts())
        out.links = {"c1": [0, 1]}
        back = from_json(json.loads(json.dumps(to_json(out))))
        assert [r.label() for r in back.routes] == [r.label() for r in out.routes] and back.links == {"c1": [0, 1]}


# ------------------------------------------------------------------ the stage


class FakeClient:
    def __init__(self, vm, alive=True):
        self.vm, self.alive = vm, alive

    def attach(self, vm_id):
        if not self.alive:
            raise AssertionError("not reached")
        return self.vm


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id",
                           (uid,)).fetchone()[0]
        return conn.execute("INSERT INTO projects (event_id, team_name, repo_url, live_url) VALUES (%s, 'T', 'https://github.com/a/b', %s) RETURNING id::text",
                            (eid, "https://t.example")).fetchone()[0]


def run_stage(pool, project_id, client, model=None):
    cfg = SimpleNamespace(sandbox=SandboxSettings("http://x", "t", 900, 600, 20))
    set_services(Services(cfg, pool, model, None, None, lambda host: None, None, sandbox=client))
    job = Job(str(uuid.uuid4()), "route_discovery", "python", "project", project_id, {}, "hackathon", 1, 1, 3, 60)
    try:
        return stage_module.route_discovery(job, JobContext(job, pool))
    finally:
        set_services(None)


class VmWithListing(FakeVm):
    def exec(self, command, **kw):
        if "git ls-files" in command:
            return ExecResult(0, stdout="\n".join(self.files))
        return super().exec(command, **kw)


def track_of(pool, claim_id):
    with pool.connection() as conn:
        return conn.execute("SELECT track FROM claims WHERE id = %s::uuid", (claim_id,)).fetchone()[0]


class TestRouteDiscoveryStage:
    def start_run(self, pool, project, status="running"):
        run_id = create_run(pool, Subject("project", project))
        update_run(pool, run_id, status=status, resources={"vm_id": "vm1", "port": 3000, "app_dir": "server"})
        return run_id

    def test_routes_are_saved_with_the_run_claims_get_their_track_and_minor_claims_appear(self, pool, project):
        subject = Subject("project", project)
        (served, other) = save_claims(pool, subject, [
            Claim(text="Add an item to the list", claim_group="Core", importance=3, source="criteria"),
            Claim(text="See statistics", claim_group="Core", importance=2, source="criteria")])
        self.start_run(pool, project)
        out0 = discover(FakeVm(FILES), None, port=3000, app_dir="server", facts=facts())
        add = [r.label() for r in out0.routes].index("POST /api/items") + 1
        model = Model({"links": [{"claim": 1, "routes": [add]}] if load_claims(pool, subject)[0].text == served.text else [{"claim": 2, "routes": [add]}], "routes": []})

        result = run_stage(pool, project, FakeClient(VmWithListing(FILES)), model)
        assert result["routes"] == 6 and result["claims_linked"] == 1 and result["minor_claims"] >= 3
        run = latest_run(pool, subject)
        saved = run.resources["discovery"]
        assert len(saved["routes"]) == 6 and len(saved["links"]) == 1 + result["minor_claims"]
        # the project also has a live link, so a served claim is tested by both tracks
        linked_claim_ids = [cid for cid in saved["links"] if track_of(pool, cid) == "both"]
        assert len(linked_claim_ids) == 1

    def test_running_it_again_does_not_pile_up_minor_claims(self, pool, project):
        self.start_run(pool, project)
        run_stage(pool, project, FakeClient(VmWithListing(FILES)), None)
        first = sorted(c.text for c in load_claims(pool, Subject("project", project)))
        assert first  # the minor claims exist
        run_stage(pool, project, FakeClient(VmWithListing(FILES)), None)
        assert sorted(c.text for c in load_claims(pool, Subject("project", project))) == first

    def test_an_app_that_is_not_running_is_skipped_with_the_reason(self, pool, project):
        run_id = self.start_run(pool, project, status="could_not_run")
        update_run(pool, run_id, status_detail="could not run: the install step failed")
        out = run_stage(pool, project, FakeClient(None))
        assert out["skipped"] and "install step failed" in out["reason"]

    def test_no_run_at_all_is_skipped(self, pool, project):
        assert run_stage(pool, project, FakeClient(None))["skipped"]

    def test_a_vm_that_has_ended_makes_the_run_could_not_run_not_an_error(self, pool, project):
        class Gone(VmWithListing):
            def exec(self, command, **kw):
                raise SandboxError("that VM no longer exists")

        self.start_run(pool, project)
        out = run_stage(pool, project, FakeClient(Gone(FILES)))
        assert out["skipped"] and latest_run(pool, Subject("project", project)).status == "could_not_run"
