"""Backend tests over HTTP: plans, running them, judging answers, proof records, and the planner."""
import json
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from talnex_ai.claims.store import Subject, save_claims
from talnex_ai.formats import Claim
from talnex_ai.safety.site_rules import LimitReached
from talnex_ai.sandbox.api_tests.executor import dig, execute, expectation_text, fill, judge_answer, run_http_plan
from talnex_ai.sandbox.api_tests.plan import (
    MAX_BODY_CHARS, HttpPlan, HttpStep, access_plan, concrete_path, edge_plan, load_plan, sample_body, smoke_plan,
)
from talnex_ai.sandbox.api_tests.planner import applicable_types, check_plans, plan_claim_http, route_line
from talnex_ai.sandbox.api_tests.proof import check_http_proof, transcript
from talnex_ai.sandbox.client import HttpResult
from talnex_ai.sandbox.route_discovery import Route
from talnex_ai.testing.runner import store


def res(status=200, body="", error=None, headers=None):
    return HttpResult(status=status, body=body.encode() if isinstance(body, str) else json.dumps(body).encode(),
                      error=error, headers=headers or {})


class FakeApi:
    """Answers by 'METHOD /path'. A list is used in turn; the last answer repeats."""

    def __init__(self, **script):
        self.script = {k.replace("_", " ", 1): v for k, v in script.items()}
        self.sent = []

    def request(self, method, port, path, **kw):
        self.sent.append((method, path, kw))
        answer = self.script.get(f"{method} {path}")
        if answer is None:
            return res(404, "not found")
        if isinstance(answer, list):
            return answer.pop(0) if len(answer) > 1 else answer[0]
        return answer


class Sink:
    def __init__(self):
        self.put = {}

    def put_bytes(self, key, data, content_type=""):
        self.put[key] = data

    def get_bytes(self, key):
        return self.put[key]


# ------------------------------------------------------------------ plans


class TestPlanGuards:
    def test_a_delete_must_name_a_record_the_plan_made(self):
        with pytest.raises(ValidationError):
            HttpStep(method="DELETE", path="/api/items")
        assert HttpStep(method="DELETE", path="/api/items/{id}").method == "DELETE"

    def test_paths_must_be_paths_and_bodies_must_be_one_kind(self):
        for bad in ({"path": "api/items"}, {"path": "/a b"}, {"path": "/x", "json_body": {}, "raw_body": "x"}):
            with pytest.raises(ValidationError):
                HttpStep(**bad)

    def test_a_plan_has_steps_and_an_expected_result(self):
        with pytest.raises(ValidationError):
            HttpPlan(test_type="normal", steps=[], expected_result="it works")


class TestBuilders:
    def test_helpers(self):
        assert concrete_path("/items/:id/likes/{lid}") == "/items/1/likes/1" and sample_body(["a"]) == {"a": "TalNex test a"}

    def test_smoke_for_reads_and_writes_and_never_for_deletes(self):
        get = smoke_plan("GET", "/items/:id")
        assert get.steps[0].path == "/items/1" and get.steps[0].expect_below == 500 and 404 in get.steps[0].soft_status
        post = smoke_plan("POST", "/items", ["name"])
        assert post.steps[0].json_body == {"name": "TalNex test name"}
        assert smoke_plan("DELETE", "/items/:id") is None
        assert smoke_plan("ANY", "/ping").steps[0].method == "GET"

    def test_edge_cases_for_a_write_route(self):
        plan = edge_plan("POST", "/items", ["name", "price"])
        notes = [s.note for s in plan.steps]
        assert plan.test_type == "edge_case" and "an empty JSON body" in notes and "a body that is not JSON" in notes
        assert any("missing" in n for n in notes) and any("very long" in n for n in notes)
        assert any("plain text where a number" in n for n in notes) and any("an object" in n for n in notes)
        assert all(s.expect_below == 500 and 401 in s.soft_status for s in plan.steps)

    def test_edge_cases_for_a_route_with_many_fields_stay_within_the_body_limit(self):
        # Seen on the planted ShelfMate app: PATCH /api/books/:id has several fields, and five thousand characters in each of
        # four fields went over the body limit, which dropped the whole sandbox plan.
        plan = edge_plan("PATCH", "/api/books/:id", ["title", "author", "notes", "status", "rating"])
        long_steps = [s for s in plan.steps if "very long" in s.note]
        assert len(long_steps) == 1
        longest = max(len(v) for v in long_steps[0].json_body.values())
        assert longest >= 1000   # still long enough to test a length check
        assert all(len(repr(s.json_body)) <= MAX_BODY_CHARS for s in plan.steps if s.json_body is not None)

    def test_edge_cases_for_a_route_with_an_id_treat_404_as_a_good_answer(self):
        plan = edge_plan("GET", "/items/:id")
        assert [s.path for s in plan.steps] == ["/items/999999999", "/items/abc", "/items/-1"]
        assert all(404 not in s.soft_status for s in plan.steps)

    def test_a_route_with_nothing_to_vary_has_no_edge_plan(self):
        assert edge_plan("GET", "/health") is None

    def test_access_asks_for_a_turn_away_with_no_token_and_with_a_wrong_one(self):
        plan = access_plan([("GET", "/me", []), ("POST", "/items", ["name"])])
        assert [s.expect_status for s in plan.steps] == [[401, 403]] * 4
        assert plan.steps[1].headers["Authorization"].startswith("Bearer ") and not plan.steps[0].headers
        assert access_plan([]) is None

    def test_load_is_ten_at_once_then_one_more(self):
        plan = load_plan("/items")
        assert [s.parallel for s in plan.steps] == [10, 1]


# ------------------------------------------------------------------ judging and running


class TestJudging:
    def test_default_is_any_2xx(self):
        step = HttpStep(path="/x")
        assert judge_answer(step, res(201))[0] == "pass" and judge_answer(step, res(404))[0] == "fail"

    def test_expected_statuses_and_below(self):
        assert judge_answer(HttpStep(path="/x", expect_status=[401, 403]), res(403))[0] == "pass"
        assert judge_answer(HttpStep(path="/x", expect_status=[401]), res(200))[0] == "fail"
        assert judge_answer(HttpStep(path="/x", expect_below=500), res(422))[0] == "pass"
        assert judge_answer(HttpStep(path="/x", expect_below=500), res(500))[0] == "fail"

    def test_soft_statuses_are_checked_first_and_mean_could_not_confirm(self):
        step = HttpStep(path="/x", expect_below=500, soft_status=[401, 404])
        assert judge_answer(step, res(401))[0] == "unconfirmed" and judge_answer(step, res(404))[0] == "unconfirmed"

    def test_contains_and_json_keys(self):
        step = HttpStep(path="/x", expect_contains=["hello"], expect_json_keys=["id"])
        assert judge_answer(step, res(200, {"id": 1, "msg": "Hello there"}))[0] == "pass"
        assert "does not contain" in judge_answer(step, res(200, {"id": 1}))[1]
        assert "lacks id" in judge_answer(HttpStep(path="/x", expect_json_keys=["id"]), res(200, {"name": "a"}))[1]
        assert judge_answer(HttpStep(path="/x", expect_json_keys=["id"]), res(200, [{"id": 5}]))[0] == "pass"
        assert "not JSON" in judge_answer(HttpStep(path="/x", expect_json_keys=["id"]), res(200, "<html>"))[1]

    def test_no_answer_is_a_failure_but_a_slow_one_in_a_burst_is_unconfirmed(self):
        assert judge_answer(HttpStep(path="/x"), HttpResult(0, error="connection refused"))[0] == "fail"
        slow = HttpResult(0, error="the app did not answer in time")
        assert judge_answer(HttpStep(path="/x", parallel=10), slow)[0] == "unconfirmed"
        assert judge_answer(HttpStep(path="/x"), slow)[0] == "fail"

    def test_helpers(self):
        assert fill({"a": ["/x/{id}"]}, {"id": "7"}) == {"a": ["/x/7"]} and dig({"d": {"i": [{"id": 9}]}}, "d.i.0.id") == "9"
        assert dig({"a": 1}, "b") is None and dig({"a": {"b": 1}}, "a") is None
        with pytest.raises(KeyError):
            fill("/x/{missing}", {})
        assert expectation_text(HttpStep(path="/x", expect_status=[200, 201])) == "status 200 or 201"


def plan(*steps, test_type="normal"):
    return HttpPlan(test_type=test_type, steps=list(steps), expected_result="the feature works as claimed")


class TestExecute:
    def test_every_step_passing_works_and_values_flow_between_steps(self):
        api = FakeApi(POST_x=res(201, {"id": 42}), GET_x42=res(200, {"id": 42}))
        api.script["GET /items/42"] = res(200, {"id": 42, "name": "TalNex test a"})
        api.script["POST /items"] = res(201, {"id": 42})
        out, observed, steps, stop = execute(api, 3000, plan(
            HttpStep(method="POST", path="/items", json_body={"name": "TalNex test a"}, expect_status=[201], capture={"id": "id"}),
            HttpStep(path="/items/{id}", expect_contains=["TalNex test a"])))
        assert out == "works" and stop is None and "2 passed" in observed
        assert [s.kind for s in steps] == ["http", "http"] and steps[1].action.startswith("GET /items/42")
        assert api.sent[0][2]["headers"]["Content-Type"] == "application/json"

    def test_some_failing_is_partly_all_failing_is_broken(self):
        api = FakeApi()
        api.script["GET /a"], api.script["GET /b"] = res(200), res(500)
        assert execute(api, 1, plan(HttpStep(path="/a"), HttpStep(path="/b")))[0] == "partly_works"
        assert execute(api, 1, plan(HttpStep(path="/b"), HttpStep(path="/b")))[0] == "broken"

    def test_nothing_judgeable_is_blocked_not_broken(self):
        api = FakeApi()
        api.script["GET /me"] = res(401)
        out, observed, _, stop = execute(api, 1, plan(HttpStep(path="/me", expect_below=500, soft_status=[401])))
        assert out == "blocked" and "could not be confirmed" in (stop or "") or "no step could be judged" in observed

    def test_an_app_that_does_not_answer_at_all_is_blocked(self):
        api = FakeApi()
        api.script["GET /a"] = HttpResult(0, error="connection refused: nothing is listening on port 3000")
        out, _, steps, stop = execute(api, 1, plan(HttpStep(path="/a"), HttpStep(path="/b")))
        assert out == "blocked" and len(steps) == 1 and "not answering" in stop

    def test_a_step_that_needs_a_value_never_captured_is_unconfirmed(self):
        api = FakeApi()
        api.script["POST /items"] = res(500)
        out, _, steps, _ = execute(api, 1, plan(HttpStep(method="POST", path="/items", capture={"id": "id"}),
                                                  HttpStep(path="/items/{id}")))
        assert out == "broken" and "unconfirmed" in steps[1].observed

    def test_a_session_cookie_from_sign_in_is_carried_to_later_steps_like_a_browser_does(self):
        # Seen on the planted ShelfMate app: its sign-in answers with a session cookie and no token in the body, so the steps
        # after sign-in could not be confirmed.
        api = FakeApi()
        api.script["POST /login"] = res(200, {"email": "a@b.c"}, headers={"Set-Cookie": ["sm_session=abc123; Path=/; HttpOnly; SameSite=Lax"]})
        api.script["GET /me"] = res(200, {"email": "a@b.c"})
        saved = {}
        jar = {}
        out, _, _, _ = execute(api, 1, plan(HttpStep(method="POST", path="/login", json_body={"email": "a@b.c"}),
                                            HttpStep(path="/me"), HttpStep(path="/me", anonymous=True)),
                               lambda n, r: (saved.__setitem__(n, r), f"k{n}")[1], cookies_out=jar)
        assert out == "works"
        assert "Cookie" not in api.sent[0][2]["headers"]
        assert api.sent[1][2]["headers"]["Cookie"] == "sm_session=abc123"
        assert "Cookie" not in api.sent[2][2]["headers"]          # an anonymous step goes without the session
        assert jar == {"sm_session": "abc123"}
        assert saved[2]["request"]["headers"]["Cookie"] == "***"  # a session value is never kept in the saved proof

    def test_a_missing_token_key_is_fine_when_the_answer_set_a_session_cookie(self):
        # Seen on the planted ShelfMate app: the sign-in step expected a "token" key, the app answered with a session cookie, and a
        # working sign-in was reported as "a test step failed: the JSON lacks token".
        cookie = {"Set-Cookie": ["sm_session=abc; Path=/; HttpOnly"]}
        step = HttpStep(method="POST", path="/login", expect_json_keys=["token"], capture={"token": "token"})
        assert judge_answer(step, res(200, {"email": "a@b.c"}, headers=cookie))[0] == "pass"
        assert judge_answer(step, res(200, {"email": "a@b.c"}))[0] == "fail"                       # no cookie: the key really is missing
        other = HttpStep(method="POST", path="/login", expect_json_keys=["email", "token"])
        assert judge_answer(other, res(200, {"token": "t"}, headers=cookie))[0] == "fail"        # a key that is not a token still counts
        assert judge_answer(step, res(500, {"error": "x"}, headers=cookie))[0] == "fail"          # the status is still checked

    def test_a_step_that_needs_a_token_never_captured_uses_the_session_cookie_instead(self):
        api = FakeApi()
        api.script["POST /login"] = res(200, {"email": "a@b.c"}, headers={"Set-Cookie": ["sm_session=abc; Path=/"]})
        api.script["GET /me"] = res(200, {"email": "a@b.c"})
        out, _, steps, _ = execute(api, 1, plan(HttpStep(method="POST", path="/login", capture={"token": "token"}),
                                               HttpStep(path="/me", headers={"Authorization": "Bearer {token}"})))
        assert out == "works" and "unconfirmed" not in steps[1].observed
        assert "Authorization" not in api.sent[1][2]["headers"] and api.sent[1][2]["headers"]["Cookie"] == "sm_session=abc"

    def test_a_cookie_the_app_clears_is_forgotten(self):
        api = FakeApi()
        api.script["POST /login"] = res(200, headers={"Set-Cookie": ["sm_session=abc123; Path=/"]})
        api.script["POST /logout"] = res(200, headers={"Set-Cookie": ["sm_session=; Path=/; Max-Age=0"]})
        api.script["GET /me"] = res(401)
        jar = {}
        execute(api, 1, plan(HttpStep(method="POST", path="/login"), HttpStep(method="POST", path="/logout"),
                             HttpStep(path="/me", expect_below=500, soft_status=[401])), cookies_out=jar)
        assert jar == {} and "Cookie" not in api.sent[2][2]["headers"]

    def test_a_burst_sends_all_requests_and_passes_only_if_all_pass(self):
        api = FakeApi()
        api.script["GET /a"] = res(200)
        out, observed, _, _ = execute(api, 1, plan(HttpStep(path="/a", parallel=10, expect_below=500)))
        assert out == "works" and len(api.sent) == 10
        api.script["GET /a"] = [res(200)] * 3 + [res(500)]
        assert execute(api, 1, plan(HttpStep(path="/a", parallel=4, expect_below=500)))[0] == "broken"

    def test_authorization_is_hidden_in_the_proof_record(self):
        saved = {}
        api = FakeApi()
        api.script["GET /me"] = res(200)
        execute(api, 1, plan(HttpStep(path="/me", headers={"Authorization": "Bearer secret-token"})), lambda n, r: (saved.__setitem__(n, r), f"k{n}")[1])
        assert saved[1]["request"]["headers"]["Authorization"] == "***" and "secret-token" not in json.dumps(saved)


# ------------------------------------------------------------------ saved runs


@pytest.fixture
def claim(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id",
                           (uid,)).fetchone()[0]
        pid = conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s, 'T', 'https://github.com/a/b') RETURNING id::text", (eid,)).fetchone()[0]
    (c,) = save_claims(pool, Subject("project", pid), [Claim(text="List the items", claim_group="Core", importance=3, source="route", track="sandbox")])
    return pid, c


class TestRunHttpPlan:
    def test_a_run_is_saved_with_its_steps_and_proof_files(self, pool, claim):
        pid, c = claim
        api, sink = FakeApi(), Sink()
        api.script["GET /items"] = res(200, [{"id": 1}])
        rec = run_http_plan(pool=pool, files=sink, vm=api, port=3000, claim=c, plan=plan(HttpStep(path="/items")), subject_id=pid, max_tries_per_claim=3)
        assert rec.outcome == "works" and rec.try_number == 1 and rec.steps[0].proof_key in sink.put
        saved = json.loads(sink.put[rec.steps[0].proof_key])
        assert saved["request"]["path"] == "/items" and saved["responses"][0]["status"] == 200
        with pool.connection() as conn:
            row = conn.execute("SELECT track, test_type, method, outcome FROM test_runs WHERE id = %s::uuid", (rec.run_id,)).fetchone()
        assert row == ("sandbox", "normal", "http", "passed")
        assert [(s.kind, s.step_number) for s in store.load_steps(pool, rec.run_id)] == [("http", 1)]

    def test_a_broken_run_is_recorded_as_failed_and_a_blocked_one_as_blocked(self, pool, claim):
        pid, c = claim
        api = FakeApi()
        api.script["GET /items"] = res(500)
        rec = run_http_plan(pool=pool, files=Sink(), vm=api, port=1, claim=c, plan=plan(HttpStep(path="/items")), subject_id=pid, max_tries_per_claim=3)
        with pool.connection() as conn:
            assert conn.execute("SELECT outcome FROM test_runs WHERE id = %s::uuid", (rec.run_id,)).fetchone()[0] == "failed"
        api.script["GET /items"] = HttpResult(0, error="connection refused")
        rec = run_http_plan(pool=pool, files=Sink(), vm=api, port=1, claim=c, plan=plan(HttpStep(path="/items")), subject_id=pid, max_tries_per_claim=3)
        assert rec.outcome == "blocked" and rec.try_number == 2

    def test_the_tries_limit_is_enforced_per_claim(self, pool, claim):
        pid, c = claim
        api = FakeApi()
        api.script["GET /items"] = res(200)
        for _ in range(2):
            run_http_plan(pool=pool, files=Sink(), vm=api, port=1, claim=c, plan=plan(HttpStep(path="/items")), subject_id=pid, max_tries_per_claim=2)
        with pytest.raises(LimitReached):
            run_http_plan(pool=pool, files=Sink(), vm=api, port=1, claim=c, plan=plan(HttpStep(path="/items")), subject_id=pid, max_tries_per_claim=2)

    def test_a_problem_on_our_side_is_blocked_never_broken(self, pool, claim):
        pid, c = claim

        class Boom(FakeApi):
            def request(self, *a, **k):
                raise RuntimeError("docker exploded")

        rec = run_http_plan(pool=pool, files=Sink(), vm=Boom(), port=1, claim=c, plan=plan(HttpStep(path="/items")), subject_id=pid, max_tries_per_claim=3)
        assert rec.outcome == "blocked" and "on our side" in (rec.stop_reason or "")


# ------------------------------------------------------------------ independent check


class Model:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, role, messages, **kw):
        self.calls.append((role, messages))
        text = self.replies.pop(0)
        return SimpleNamespace(text=text if isinstance(text, str) else json.dumps(text))


class TestProofCheck:
    RECORD = {"request": {"method": "GET", "path": "/items", "body": None}, "parallel": 1,
              "responses": [{"status": 200, "duration_ms": 12, "body": '[{"id":1}]'}], "expected": "a 2xx answer"}

    def test_the_checker_sees_only_requests_answers_and_the_expectation(self):
        sink = Sink()
        sink.put["k1"] = json.dumps(self.RECORD).encode()
        model = Model({"outcome": "works", "seen": "it lists the items", "screenshot_clear": True})
        out = check_http_proof(model, sink, claim_text="List the items", expected_result="the items are listed", proof_keys=["k1", None])
        assert out.outcome == "works" and out.images_used == 1
        role, messages = model.calls[0]
        user = messages[1]["content"]
        assert role == "proof_checker" and "GET /items" in user and "status 200" in user and "the items are listed" in user

    def test_no_records_means_blocked_and_no_model_call(self):
        model = Model()
        out = check_http_proof(model, Sink(), claim_text="x", expected_result="y", proof_keys=[None, "missing"])
        assert out.outcome == "blocked" and model.calls == []

    def test_the_transcript_mentions_bursts_and_missing_answers(self):
        rec = {**self.RECORD, "parallel": 10, "responses": [{"status": 0, "error": "connection refused"}]}
        text = transcript([rec])
        assert "10 identical requests" in text and "no answer: connection refused" in text


# ------------------------------------------------------------------ planner


ROUTES = [Route("POST", "/api/items", "code", body_fields=["name"], needs_auth=True), Route("GET", "/api/items", "code"),
          Route("DELETE", "/api/items/:id", "code"), Route("POST", "/api/login", "code")]


def plan_json(*steps, test_type="normal", expected="the created item appears in the list"):
    return {"test_type": test_type, "steps": list(steps), "expected_result": expected}


class TestPlanner:
    def claim(self, text="Add an item and see it in the list", importance=3):
        return Claim(id="c1", text=text, claim_group="Core", importance=importance, source="criteria")

    def test_which_plans_are_written(self):
        assert applicable_types(self.claim()) == ["normal", "repeat"]
        assert applicable_types(self.claim("Calculate the total price", importance=2)) == ["normal", "known_answer"]
        assert applicable_types(Claim(text="Cannot try this", claim_group="Core", importance=1, source="resume", testable=False,
                                      untestable_reason="a measurement")) == []

    def test_a_good_plan_is_accepted_and_tied_to_the_claim(self):
        good = plan_json({"method": "POST", "path": "/api/items", "json_body": {"name": "TalNex test a"}, "expect_status": [201], "capture": {"id": "id"}},
                         {"method": "GET", "path": "/api/items", "expect_contains": ["TalNex test a"]},
                         {"method": "DELETE", "path": "/api/items/{id}"})
        repeat = plan_json({"method": "GET", "path": "/api/items"}, {"method": "GET", "path": "/api/items"}, test_type="repeat", expected="both lists are the same")
        model = Model({"plans": [good, repeat]})
        plans = plan_claim_http(model, self.claim(), ROUTES)
        assert [p.test_type for p in plans] == ["normal", "repeat"] and all(p.claim_id == "c1" for p in plans)
        assert "POST /api/items  (body fields: name; needs a sign-in token)" in model.calls[0][1][1]["content"]

    def test_an_invented_route_gets_one_repair_try(self):
        bad = plan_json({"method": "GET", "path": "/api/secret"})
        good = plan_json({"method": "GET", "path": "/api/items"})
        model = Model({"plans": [bad]}, {"plans": [good]})
        plans = plan_claim_http(model, self.claim(importance=1), ROUTES)
        assert len(plans) == 1 and len(model.calls) == 2 and "not one of the listed routes" in model.calls[1][1][-1]["content"]

    def test_a_hedged_expected_result_is_rejected(self):
        hedged = plan_json({"method": "GET", "path": "/api/items"}, expected="the item is listed, or confirmed absent")
        with pytest.raises(Exception):
            plan_claim_http(Model({"plans": [hedged]}, {"plans": [hedged]}), self.claim(importance=1), ROUTES)

    def test_route_shapes_ignore_ids_and_spelling(self):
        plans = [HttpPlan.model_validate(plan_json({"method": "GET", "path": "/api/items?page=2"}, {"method": "POST", "path": "/api/login"},
                                                   {"method": "DELETE", "path": "/api/items/{id}"}))]
        assert check_plans(plans, ["normal"], ROUTES) == plans

    def test_route_lines_say_what_the_planner_needs_to_know(self):
        assert route_line(ROUTES[0]) == "POST /api/items  (body fields: name; needs a sign-in token)" and route_line(ROUTES[1]) == "GET /api/items"


# ------------------------------------------------------------------ the sign-in token


class TestSignInToken:
    def test_the_token_goes_on_every_step_except_anonymous_ones_and_a_step_may_set_its_own(self):
        api = FakeApi()
        api.script.update({"GET /a": res(200), "GET /b": res(200), "GET /c": res(200)})
        execute(api, 1, plan(HttpStep(path="/a"), HttpStep(path="/b", anonymous=True),
                             HttpStep(path="/c", headers={"authorization": "Bearer mine"})),
                default_headers={"Authorization": "Bearer abc"})
        headers = [kw["headers"] for _, _, kw in api.sent]
        assert headers[0] == {"Authorization": "Bearer abc"} and headers[1] == {} and headers[2] == {"authorization": "Bearer mine"}

    def test_access_checks_are_anonymous_so_a_token_never_hides_a_missing_check(self):
        assert all(s.anonymous for s in access_plan([("GET", "/me", [])]).steps)

    def test_captured_values_are_handed_back(self):
        api = FakeApi()
        api.script["POST /login"] = res(200, {"token": "t0k"})
        got: dict = {}
        execute(api, 1, plan(HttpStep(method="POST", path="/login", capture={"token": "token"})), variables_out=got)
        assert got["token"] == "t0k"

    def test_the_header_that_worked_is_read_from_the_plan(self):
        from talnex_ai.sandbox.api_tests.derive import auth_header_from
        p = plan(HttpStep(method="POST", path="/login", capture={"token": "token"}), HttpStep(path="/me", headers={"Authorization": "Bearer {token}"}))
        assert auth_header_from(p, {"token": "xyz"}) == {"Authorization": "Bearer xyz"}
        assert auth_header_from(p, {}) == {} and auth_header_from(plan(HttpStep(path="/x")), {"token": "t"}) == {}

    def test_later_tests_send_the_token_when_there_is_one_else_the_session_cookie(self):
        from talnex_ai.sandbox.api_tests.derive import session_header_from
        with_token = plan(HttpStep(method="POST", path="/login", capture={"token": "token"}), HttpStep(path="/me", headers={"Authorization": "Bearer {token}"}))
        no_token = plan(HttpStep(method="POST", path="/login"), HttpStep(path="/me"))
        assert session_header_from(with_token, {"token": "xyz"}, {"sid": "c"}) == {"Authorization": "Bearer xyz"}
        assert session_header_from(no_token, {}, {"sid": "c", "theme": "dark"}) == {"Cookie": "sid=c; theme=dark"}
        assert session_header_from(no_token, {}, {}) == {}


class TestRealValuesMatchRouteParameters:
    def routes(self):
        return [Route("POST", "/api/tokens/oauth2/<provider>", "code"), Route("GET", "/api/users/<int:id>/posts", "code"), Route("GET", "/api/items", "code")]

    def plans(self, *paths):
        return [HttpPlan.model_validate(plan_json(*({"method": m, "path": p} for m, p in paths)))]

    def test_a_real_value_fits_a_parameter_of_the_route(self):
        ok = self.plans(("POST", "/api/tokens/oauth2/google"), ("GET", "/api/users/42/posts"), ("GET", "/api/users/{id}/posts"), ("GET", "/api/items?page=2"))
        assert check_plans(ok, ["normal"], self.routes()) == ok

    def test_a_route_that_is_not_listed_is_still_refused(self):
        for bad in (("GET", "/api/secret"), ("GET", "/api/users/42"), ("DELETE", "/api/items/{id}"), ("POST", "/api/items")):
            with pytest.raises(Exception):
                check_plans(self.plans(bad), ["normal"], self.routes())


class TestEveryRunGetsAFreshValue:
    def test_run_is_filled_in_and_is_different_each_time_so_sign_ups_never_collide(self):
        api = FakeApi()
        api.script["POST /api/users"] = res(201)
        step = HttpStep(method="POST", path="/api/users", json_body={"email": "talnex-{run}@example.com", "username": "talnex{run}"}, expect_status=[201])
        execute(api, 1, plan(step))
        execute(api, 1, plan(step))
        bodies = [json.loads(kw["body"]) for _, _, kw in api.sent]
        assert bodies[0]["email"].startswith("talnex-") and "{run}" not in bodies[0]["email"] and bodies[0]["email"] != bodies[1]["email"]
        assert bodies[0]["username"] == "talnex" + bodies[0]["email"][len("talnex-"):-len("@example.com")]

    def test_a_plan_can_reuse_the_value_in_a_later_step(self):
        api = FakeApi()
        api.script["POST /api/users"] = res(201)
        api.script["POST /api/tokens"] = res(200, {"token": "t"})
        got: dict = {}
        execute(api, 1, plan(HttpStep(method="POST", path="/api/users", json_body={"email": "talnex-{run}@example.com"}, expect_status=[201]),
                             HttpStep(method="POST", path="/api/tokens", json_body={"email": "talnex-{run}@example.com"})), variables_out=got)
        first, second = (json.loads(kw["body"])["email"] for _, _, kw in api.sent)
        assert first == second == f"talnex-{got['run']}@example.com"

    def test_the_planner_is_told_about_it(self):
        from talnex_ai.llm.prompts.http_test_planner import SYSTEM
        assert "{run}" in SYSTEM and "Never write a fixed email" in SYSTEM

    def test_the_planner_is_told_a_session_may_be_a_cookie(self):
        from talnex_ai.llm.prompts.http_test_planner import SYSTEM
        assert "session cookie" in SYSTEM and "do not ask for a token" in SYSTEM

    def test_the_planner_must_change_a_value_before_it_expects_the_changed_number(self):
        # The planted ShelfMate goal bar: the route answered 200 with the goal and a count of 0 whatever was finished.
        from talnex_ai.llm.prompts.http_test_planner import SYSTEM
        assert "send the requests that should change it" in SYSTEM and "starting point" in SYSTEM


class TestBasicSignInAndExpectedValues:
    def test_a_basic_auth_step_gets_a_built_header_that_is_hidden_in_the_proof(self):
        import base64
        saved = {}
        api = FakeApi()
        api.script["POST /api/tokens"] = res(200, {"token": "t"})
        step = HttpStep(method="POST", path="/api/tokens", basic_auth={"username": "talnex-{run}@example.com", "password": "pw"}, capture={"token": "token"})
        got: dict = {}
        execute(api, 1, plan(step), lambda n, r: (saved.__setitem__(n, r), f"k{n}")[1], variables_out=got)
        sent = api.sent[0][2]["headers"]["Authorization"]
        assert sent == "Basic " + base64.b64encode(f"talnex-{got['run']}@example.com:pw".encode()).decode()
        assert saved[1]["request"]["headers"]["Authorization"] == "***" and got["token"] == "t"

    def test_basic_auth_replaces_a_token_that_would_be_sent_by_default(self):
        api = FakeApi()
        api.script["POST /api/tokens"] = res(200)
        execute(api, 1, plan(HttpStep(method="POST", path="/api/tokens", basic_auth={"username": "a", "password": "b"})),
                default_headers={"Authorization": "Bearer old"})
        assert api.sent[0][2]["headers"]["Authorization"].startswith("Basic ")

    def test_basic_auth_needs_exactly_a_username_and_a_password(self):
        with pytest.raises(ValidationError):
            HttpStep(path="/x", basic_auth={"username": "a"})

    def test_the_value_of_run_is_put_into_what_an_answer_must_contain(self):
        api = FakeApi()
        api.script["POST /api/posts"] = lambda: None
        seen = {}

        def answer(method, port, path, **kw):
            seen["body"] = json.loads(kw["body"])
            return res(201, json.dumps({"text": seen["body"]["text"]}))

        api.request = answer
        out, _, _, _ = execute(api, 1, plan(HttpStep(method="POST", path="/api/posts", json_body={"text": "TalNex test post {run}"},
                                                      expect_status=[201], expect_contains=["TalNex test post {run}"])))
        assert out == "works"


class TestEdgeCasesUseARealRecord:
    def test_the_collection_path_stops_at_the_first_parameter(self):
        from talnex_ai.sandbox.api_tests.plan import collection_path
        assert collection_path("/api/books/:id/rating") == "/api/books" and collection_path("/api/books/{id}") == "/api/books" and collection_path("/a/b") == "/a/b"

    def test_a_record_is_made_first_and_its_id_is_used_for_the_bad_input(self):
        plan = edge_plan("POST", "/api/books/:id/rating", ["stars"], record_source=("/api/books", ["title"]))
        first = plan.steps[0]
        assert (first.method, first.path, first.json_body) == ("POST", "/api/books", {"title": "TalNex test title"}) and first.capture == {"rid": "id|_id|data.id|uuid|pk"}
        bad = [s for s in plan.steps[1:] if "plain text" in s.note][0]
        assert bad.path == "/api/books/{rid}/rating" and bad.json_body == {"stars": "abc"}
        # the checks on an id that does not exist still use made-up ids
        assert any(s.path == "/api/books/999999999/rating" for s in plan.steps)

    def test_without_a_way_to_make_a_record_nothing_changes(self):
        plan = edge_plan("POST", "/api/books/:id/rating", ["stars"])
        assert plan.steps[0].note == "an empty JSON body" and plan.steps[0].path == "/api/books/1/rating"

    def test_the_first_found_place_wins_for_an_id(self):
        assert dig({"_id": "abc"}, "id|_id|data.id") == "abc" and dig({"data": {"id": 5}}, "id|_id|data.id") == "5" and dig({}, "id|_id") is None

    def test_a_record_made_in_the_run_is_really_used_by_the_following_steps(self):
        api = FakeApi()
        api.script["POST /api/books"] = res(201, {"id": 7})
        api.script["POST /api/books/7/rating"] = res(400, {"error": "stars must be a number"})
        out = execute(api, 1, edge_plan("POST", "/api/books/:id/rating", ["stars"], record_source=("/api/books", ["title"])))[0]
        assert ("POST", "/api/books/7/rating") in [(m, p) for m, p, _ in api.sent] and out in ("works", "partly_works")

    def test_derive_finds_the_collections_post_route(self):
        from talnex_ai.sandbox.api_tests.derive import derive
        routes = [Route("POST", "/api/books", "code", body_fields=["title"]), Route("POST", "/api/books/:id/rating", "code", body_fields=["stars"])]
        plan = derive(routes).plans["POST /api/books/:id/rating answers bad input without crashing"]
        assert plan.steps[0].path == "/api/books" and plan.steps[0].note.startswith("make a record")
