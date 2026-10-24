"""The backend-test stages: sandbox_plan, sandbox_test and sandbox_end, plus the claims TalNex derives from the routes."""
import json
import uuid
from types import SimpleNamespace

import pytest

from talnex_ai.claims.store import Subject, load_claims, save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim
from talnex_ai.sandbox.api_tests.derive import ACCESS_TEXT, LOAD_TEXT, SETUP_TEXT, derive
from talnex_ai.sandbox.client import HttpResult
from talnex_ai.sandbox.route_discovery import Route, to_json, Discovery
from talnex_ai.sandbox.store import create_run, latest_run, update_run
from talnex_ai.settings import SandboxSettings
from talnex_ai.worker.handlers import sandbox_end as end_module
from talnex_ai.worker.handlers import sandbox_plan as plan_module
from talnex_ai.worker.handlers import sandbox_test as test_module
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services

ROUTES = [
    Route("GET", "/api/items", "code", "app.py", 5),
    Route("POST", "/api/items", "code", "app.py", 9, body_fields=["name"]),
    Route("GET", "/api/items/:id", "code", "app.py", 14),
    Route("DELETE", "/api/items/:id", "code", "app.py", 20),
    Route("GET", "/api/me", "code", "app.py", 30, needs_auth=True),
    Route("GET", "/health", "code", "app.py", 2),
]


def res(status=200, body="{}", error=None):
    return HttpResult(status=status, body=body.encode(), error=error)


class FakeApp:
    """The app inside the VM: answers by 'METHOD /path', 404 otherwise. Also reads source for the planner's snippets."""

    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.sent = []
        self.destroyed = False

    def request(self, method, port, path, **kw):
        self.sent.append((method, path))
        a = self.answers.get(f"{method} {path}")
        if a is None:
            return res(404, "not found")
        if isinstance(a, list):
            return a.pop(0) if len(a) > 1 else a[0]
        return a

    def exec(self, command, **kw):
        from talnex_ai.sandbox.client import ExecResult
        return ExecResult(0, stdout="")

    def destroy(self):
        self.destroyed = True


class Client:
    def __init__(self, app):
        self.app = app

    def attach(self, vm_id):
        return self.app


class Files:
    def __init__(self):
        self.put = {}

    def put_bytes(self, key, data, content_type=""):
        self.put[key] = data

    def get_bytes(self, key):
        return self.put[key]


class Model:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, role, messages, **kw):
        self.calls.append(role)
        text = self.replies.pop(0)
        return SimpleNamespace(text=text if isinstance(text, str) else json.dumps(text))


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id",
                           (uid,)).fetchone()[0]
        return conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s, 'T', 'https://github.com/a/b') RETURNING id::text", (eid,)).fetchone()[0]


def running_run(pool, project, discovery, recipe_source="package_files"):
    subject = Subject("project", project)
    run_id = create_run(pool, subject)
    update_run(pool, run_id, status="running", recipe={"source": recipe_source, "notes": []}, build_log_key="sandbox/x/build.log",
               resources={"vm_id": "vm1", "port": 3000, "health_path": "/health", "app_dir": "", "discovery": to_json(discovery)})
    return run_id


def call(handler, pool, project, app, model=None, files=None, kind="project"):
    cfg = SimpleNamespace(sandbox=SandboxSettings("http://x", "t", 900, 600, 20),
                          limits=SimpleNamespace(max_tries_per_claim=3, extra_tests_per_claim=1, sleeping_host_wait_seconds=1))
    set_services(Services(cfg, pool, model, None, files or Files(), lambda host: None, None, sandbox=Client(app)))
    job = Job(str(uuid.uuid4()), handler.__name__, "python", kind, project, {}, "sandbox_check_project", 1, 1, 3, 3000)
    try:
        return handler(job, JobContext(job, pool))
    finally:
        set_services(None)


def save_stage_result(pool, project, name, result):
    with pool.connection() as conn:
        conn.execute("""INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, result, dedupe_key)
                        VALUES (%s, 'python', 'project', %s::uuid, 'sandbox_check_project', 1, 'done', %s::jsonb, %s)""",
                     (name, project, json.dumps(result), f"{project}:{name}"))


# ------------------------------------------------------------------ derived claims


class TestDerive:
    def test_setup_edge_access_and_load_claims_with_their_groups(self):
        d = derive(ROUTES)
        groups = {c.text: c.claim_group for c in d.claims}
        assert groups[SETUP_TEXT] == "Setup" and groups[ACCESS_TEXT] == "Access" and groups[LOAD_TEXT] == "Reliability"
        edge = [t for t, g in groups.items() if g == "Edge cases"]
        assert "POST /api/items answers bad input without crashing" in edge and "GET /api/items/:id answers bad input without crashing" in edge
        assert not any("DELETE" in t for t in edge) and all(c.track == "sandbox" for c in d.claims)
        assert set(d.plans) == set(groups) - {SETUP_TEXT}

    def test_routes_that_serve_a_claim_get_their_edge_claim_first_and_there_are_at_most_eight(self):
        many = [Route("POST", f"/r{i}", "code", body_fields=["a"]) for i in range(20)]
        d = derive(many, served={15})
        edge = [c.text for c in d.claims if c.claim_group == "Edge cases"]
        assert len(edge) == 8 and edge[0] == "POST /r15 answers bad input without crashing"

    def test_no_protected_route_no_access_claim_and_no_open_get_no_load_claim(self):
        d = derive([Route("POST", "/x", "code", body_fields=["a"])])
        assert ACCESS_TEXT not in {c.text for c in d.claims} and LOAD_TEXT not in {c.text for c in d.claims}


CHECKLIST = {"items": [{"text": "the route is really implemented", "part": "implementation", "core": True},
                       {"text": "answers are correct", "part": "logic", "core": False},
                       {"text": "bad input is handled", "part": "edge", "core": False}]}


class RoleModel(Model):
    """Answers a planner request from its list, and every checklist request (role claim_reader) with a fixed checklist."""

    def chat(self, role, messages, **kw):
        if role == "claim_reader":
            self.calls.append(role)
            return SimpleNamespace(text=json.dumps(CHECKLIST))
        return super().chat(role, messages, **kw)


# ------------------------------------------------------------------ sandbox_plan


class TestSandboxPlan:
    def setup_claims(self, pool, project):
        subject = Subject("project", project)
        main, minor = save_claims(pool, subject, [
            Claim(text="Add an item and see it in the list", claim_group="Core", importance=2, source="criteria", track="sandbox"),
            Claim(text="The route GET /api/items/:id exists and responds sensibly", claim_group="Core", importance=1, source="route", track="sandbox"),
        ])
        return main, minor

    def test_model_plans_for_served_claims_and_code_built_plans_for_the_rest(self, pool, project):
        main, minor = self.setup_claims(pool, project)
        d = Discovery(routes=list(ROUTES), links={main.id: [0, 1], minor.id: [2]})
        running_run(pool, project, d)
        good = {"test_type": "normal", "expected_result": "the new item appears in the list",
                "steps": [{"method": "POST", "path": "/api/items", "json_body": {"name": "TalNex test a"}, "expect_status": [201]},
                          {"method": "GET", "path": "/api/items", "expect_contains": ["TalNex test a"]}]}
        model = RoleModel({"plans": [good]})
        out = call(plan_module.sandbox_plan, pool, project, FakeApp(), model)
        assert model.calls.count("test_planner") == 1 and out["routes"] == 6
        # a checklist is written for every backend claim BEFORE any test runs, including the Setup claim that has no requests
        assert set(out["checklists"]) == set(out["claims"]) | {next(c.id for c in load_claims(pool, Subject("project", project)) if c.text == SETUP_TEXT)}
        assert len(out["checklists"][main.id]["checklist"]["items"]) == 3
        plans = out["claims"]
        assert plans[main.id]["plans"][0]["test_type"] == "normal"
        assert plans[minor.id]["plans"][0]["test_type"] == "route_smoke"
        derived = {c.text: c for c in load_claims(pool, Subject("project", project))}
        assert SETUP_TEXT in derived and ACCESS_TEXT in derived
        assert plans[derived[ACCESS_TEXT].id]["plans"][0]["test_type"] == "access" and derived[SETUP_TEXT].id not in plans

    def test_a_planner_that_fails_leaves_the_claim_untested_not_broken(self, pool, project):
        main, minor = self.setup_claims(pool, project)
        running_run(pool, project, Discovery(routes=list(ROUTES), links={main.id: [0]}))
        out = call(plan_module.sandbox_plan, pool, project, FakeApp(), Model("nope", "nope"))
        assert main.id not in out["claims"] and "no test could be written" in out["errors"][main.id]

    def test_a_deleting_route_is_not_smoke_tested(self, pool, project):
        _, minor = self.setup_claims(pool, project)
        running_run(pool, project, Discovery(routes=list(ROUTES), links={minor.id: [3]}))
        out = call(plan_module.sandbox_plan, pool, project, FakeApp(), None)
        assert minor.id not in out["claims"] and "deletes" in out["errors"][minor.id]

    def test_nothing_running_or_no_routes_is_skipped(self, pool, project):
        assert call(plan_module.sandbox_plan, pool, project, FakeApp())["skipped"]
        running_run(pool, project, Discovery(routes=[]))
        assert call(plan_module.sandbox_plan, pool, project, FakeApp())["skipped"]


# ------------------------------------------------------------------ sandbox_test


def plan_dict(test_type, steps, expected="it behaves"):
    return {"test_type": test_type, "steps": steps, "expected_result": expected}


class TestSandboxTest:
    def claim(self, pool, project, text="Add an item and see it in the list", group="Core"):
        (c,) = save_claims(pool, Subject("project", project), [Claim(text=text, claim_group=group, importance=2, source="criteria", track="sandbox")])
        return c

    def verdict(self, pool, claim_id):
        with pool.connection() as conn:
            return conn.execute("SELECT verdict, confidence, reason FROM results WHERE claim_id = %s::uuid", (claim_id,)).fetchone()

    def test_a_claim_that_works_is_confirmed_by_the_independent_check(self, pool, project):
        c = self.claim(pool, project)
        running_run(pool, project, Discovery(routes=list(ROUTES)))
        save_stage_result(pool, project, "sandbox_plan", {"claims": {c.id: {"plans": [plan_dict("normal", [{"method": "GET", "path": "/api/items", "expect_status": [200]}])]}}})
        app = FakeApp({"GET /api/items": res(200, "[]"), "GET /health": res(200)})
        model = Model({"outcome": "works", "seen": "the list was returned", "screenshot_clear": True})
        out = call(test_module.sandbox_test, pool, project, app, model)
        verdict, confidence, reason = self.verdict(pool, c.id)
        assert verdict == "works" and out["verdicts"]["works"] >= 1 and "list was returned" in reason

    def test_broken_needs_two_failed_tries_and_an_agreeing_check(self, pool, project):
        c = self.claim(pool, project, "The route GET /api/items/:id exists and responds sensibly")
        running_run(pool, project, Discovery(routes=list(ROUTES)))
        steps = [{"method": "GET", "path": "/api/items/1", "expect_below": 500}]
        save_stage_result(pool, project, "sandbox_plan", {"claims": {c.id: {"plans": [plan_dict("route_smoke", steps)]}}})
        app = FakeApp({"GET /api/items/1": res(500, "Traceback"), "GET /api/items/1/": res(500, "Traceback"), "GET /health": res(200)})
        model = Model({"outcome": "broken", "seen": "a server error came back", "screenshot_clear": True})
        call(test_module.sandbox_test, pool, project, app, model)
        verdict, confidence, reason = self.verdict(pool, c.id)
        assert verdict == "broken" and ("GET", "/api/items/1/") in app.sent    # the second try was built differently

    def test_an_app_that_stopped_answering_is_could_not_test_never_broken(self, pool, project):
        c = self.claim(pool, project)
        running_run(pool, project, Discovery(routes=list(ROUTES)))
        save_stage_result(pool, project, "sandbox_plan", {"claims": {c.id: {"plans": [plan_dict("normal", [{"method": "GET", "path": "/api/items"}])]}}})
        gone = HttpResult(0, error="connection refused: nothing is listening on port 3000")
        app = FakeApp({"GET /api/items": gone, "GET /health": gone})
        call(test_module.sandbox_test, pool, project, app, Model())
        assert self.verdict(pool, c.id)[0] == "could_not_test"

    def test_a_sign_in_wall_means_could_not_confirm(self, pool, project):
        c = self.claim(pool, project, "POST /api/items answers bad input without crashing", "Edge cases")
        running_run(pool, project, Discovery(routes=list(ROUTES)))
        step = {"method": "POST", "path": "/api/items", "json_body": {}, "expect_below": 500, "soft_status": [401, 403]}
        save_stage_result(pool, project, "sandbox_plan", {"claims": {c.id: {"plans": [plan_dict("edge_case", [step, step])]}}})
        app = FakeApp({"POST /api/items": res(401), "GET /health": res(200)})
        call(test_module.sandbox_test, pool, project, app, Model())
        assert self.verdict(pool, c.id)[0] == "could_not_test"

    def test_the_setup_claim_is_judged_from_how_the_app_came_up(self, pool, project):
        c = self.claim(pool, project, SETUP_TEXT, "Setup")
        running_run(pool, project, Discovery(routes=list(ROUTES)))
        save_stage_result(pool, project, "sandbox_plan", {"claims": {"unused": {"plans": []}}})
        call(test_module.sandbox_test, pool, project, FakeApp(), Model())
        assert self.verdict(pool, c.id)[0] == "works"

    def test_a_setup_that_needed_a_model_fix_is_partly_working(self, pool, project):
        c = self.claim(pool, project, SETUP_TEXT, "Setup")
        run_id = running_run(pool, project, Discovery(routes=list(ROUTES)), recipe_source="model_fix")
        update_run(pool, run_id, recipe={"source": "model_fix", "notes": ["model fix: the Python version was too old"]})
        save_stage_result(pool, project, "sandbox_plan", {"claims": {"unused": {"plans": []}}})
        call(test_module.sandbox_test, pool, project, FakeApp(), Model())
        verdict, _, reason = self.verdict(pool, c.id)
        assert verdict == "partly_works" and "not enough" in reason

    def test_nothing_planned_or_nothing_running_is_skipped(self, pool, project):
        assert call(test_module.sandbox_test, pool, project, FakeApp(), Model())["skipped"]
        running_run(pool, project, Discovery(routes=list(ROUTES)))
        assert call(test_module.sandbox_test, pool, project, FakeApp(), Model())["skipped"]


# ------------------------------------------------------------------ sandbox_end


class TestSandboxEnd:
    def test_the_vm_is_destroyed_and_the_run_closed_and_it_is_safe_to_repeat(self, pool, project):
        running_run(pool, project, Discovery(routes=[]))
        app = FakeApp()
        out = call(end_module.sandbox_end, pool, project, app)
        assert out["destroyed"] == "vm1" and app.destroyed and latest_run(pool, Subject("project", project)).status == "done"
        assert call(end_module.sandbox_end, pool, project, app)["skipped"]

    def test_no_run_is_skipped(self, pool, project):
        assert call(end_module.sandbox_end, pool, project, FakeApp())["skipped"]


# ------------------------------------------------------------------ signing in once and using the token


AUTH_ROUTES = [Route("POST", "/api/users", "code", body_fields=["email", "password"]), Route("POST", "/api/tokens", "code", body_fields=["email", "password"]),
               Route("GET", "/api/me", "code", needs_auth=True), Route("GET", "/api/items", "code")]


def sign_in_plan():
    return {"test_type": "normal", "expected_result": "the new user signs in and the token opens a protected route",
            "steps": [{"method": "POST", "path": "/api/users", "json_body": {"email": "talnex-test@example.com", "password": "TalNex-test-1"}, "expect_status": [201]},
                      {"method": "POST", "path": "/api/tokens", "json_body": {"email": "talnex-test@example.com", "password": "TalNex-test-1"},
                       "expect_status": [200], "capture": {"token": "token"}},
                      {"method": "GET", "path": "/api/me", "headers": {"Authorization": "Bearer {token}"}, "expect_status": [200]}]}


class TestSignInClaim:
    def test_the_planner_writes_a_sign_in_plan_when_the_app_has_sign_in_routes(self, pool, project):
        from talnex_ai.sandbox.api_tests.derive import AUTH_TEXT
        running_run(pool, project, Discovery(routes=list(AUTH_ROUTES)))
        out = call(plan_module.sandbox_plan, pool, project, FakeApp(), Model({"plans": [sign_in_plan()]}))
        claim = next(c for c in load_claims(pool, Subject("project", project)) if c.text == AUTH_TEXT)
        assert claim.claim_group == "Access" and out["claims"][claim.id]["plans"][0]["steps"][1]["capture"] == {"token": "token"}

    def test_no_sign_in_routes_no_sign_in_claim(self, pool, project):
        from talnex_ai.sandbox.api_tests.derive import AUTH_TEXT
        running_run(pool, project, Discovery(routes=[Route("GET", "/api/items", "code")]))
        call(plan_module.sandbox_plan, pool, project, FakeApp(), Model())
        assert not any(c.text == AUTH_TEXT for c in load_claims(pool, Subject("project", project)))

    def test_the_sign_in_test_runs_first_and_later_tests_send_its_token(self, pool, project):
        from talnex_ai.sandbox.api_tests.derive import AUTH_TEXT
        running_run(pool, project, Discovery(routes=list(AUTH_ROUTES)))
        (auth, other) = save_claims(pool, Subject("project", project), [
            Claim(text=AUTH_TEXT, claim_group="Access", importance=2, source="route", track="sandbox"),
            Claim(text="GET /api/items answers bad input without crashing", claim_group="Edge cases", importance=2, source="route", track="sandbox")])
        items = {"test_type": "edge_case", "expected_result": "the route answers without a server error", "steps": [
            {"method": "GET", "path": "/api/items", "expect_below": 500, "note": "a normal request"}]}
        # the OTHER claim is listed first on purpose: the sign-in claim must still run first
        save_stage_result(pool, project, "sandbox_plan", {"claims": {other.id: {"plans": [items]}, auth.id: {"plans": [sign_in_plan()]}}})
        app = RecordingApp({"POST /api/users": res(201), "POST /api/tokens": res(200, '{"token": "t0k3n"}'), "GET /api/me": res(200),
                            "GET /api/items": res(200, "[]"), "GET /health": res(200)})
        model = Model({"outcome": "works", "seen": "signed in and used the token", "screenshot_clear": True},
                      {"outcome": "works", "seen": "no server error", "screenshot_clear": True})
        call(test_module.sandbox_test, pool, project, app, model)
        order = [(m, p) for m, p, _ in app.sent_kw]
        assert order.index(("POST", "/api/tokens")) < order.index(("GET", "/api/items"))
        items_call = next(kw for m, p, kw in app.sent_kw if (m, p) == ("GET", "/api/items"))
        assert items_call["headers"] == {"Authorization": "Bearer t0k3n"}
        with pool.connection() as conn:
            assert conn.execute("SELECT verdict FROM results WHERE claim_id = %s::uuid", (auth.id,)).fetchone()[0] == "works"


class RecordingApp(FakeApp):
    def __init__(self, answers=None):
        super().__init__(answers)
        self.sent_kw = []

    def request(self, method, port, path, **kw):
        self.sent_kw.append((method, path, kw))
        return super().request(method, port, path, **kw)
