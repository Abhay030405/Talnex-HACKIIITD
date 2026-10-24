import json

import httpx
import pytest

from talnex_ai import settings
from talnex_ai.llm.models import model_for
from talnex_ai.llm.openrouter import OpenRouterClient, OpenRouterError

ENV = {
    "DATABASE_URL": "postgres://x", "S3_ENDPOINT": "http://s3:9000", "S3_REGION": "auto", "S3_BUCKET": "b",
    "S3_ACCESS_KEY": "a", "S3_SECRET_KEY": "s", "OPENROUTER_BASE_URL": "https://openrouter.test/api/v1",
    "OPENROUTER_API_KEY": "sk-test", "MODEL_TEST_PLANNER": "vendor/planner", "OPENROUTER_MAX_RETRIES": "2",
    "TINYFISH_AGENT_BASE_URL": "https://agent.tf.test", "TINYFISH_BROWSER_BASE_URL": "https://browser.tf.test",
    "TINYFISH_FETCH_BASE_URL": "https://fetch.tf.test",
}


def answer(text="{}", *, cost=0.002, finish="stop", model="vendor/planner"):
    return {"model": model, "choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": cost}}


class FakeServer:
    """Plays OpenRouter: hands back the queued replies in order and records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, body, headers = reply if len(reply) == 3 else (*reply, {})
        return httpx.Response(status, json=body, headers=headers)


def client(server, env=None, logged=None):
    cfg = settings.load(dict(ENV, **(env or {}))).llm
    waits = []
    c = OpenRouterClient(cfg, (lambda **row: logged.append(row)) if logged is not None else None,
                         http=httpx.Client(transport=httpx.MockTransport(server)), sleep=waits.append)
    return c, waits


def test_a_call_sends_the_role_model_and_logs_usage():
    server, logged = FakeServer((200, answer('{"ok": true}'))), []
    c, _ = client(server, logged=logged)
    result = c.chat("test_planner", [{"role": "user", "content": "plan it"}], job_id="j1")

    sent = json.loads(server.requests[0].content)
    assert server.requests[0].url == "https://openrouter.test/api/v1/chat/completions"
    assert server.requests[0].headers["authorization"] == "Bearer sk-test"
    assert sent["model"] == "vendor/planner" and sent["temperature"] == 0.1 and sent["max_tokens"] == 16384
    assert sent["usage"] == {"include": True}
    assert result.text == '{"ok": true}' and result.cost_usd == 0.002 and not result.truncated
    assert logged == [{"service": "openrouter", "model": "vendor/planner", "job_id": "j1", "tokens_in": 100,
                       "tokens_out": 20, "duration_ms": result.duration_ms, "cost_usd": 0.002}]


def test_per_call_overrides():
    server = FakeServer((200, answer()))
    c, _ = client(server)
    c.chat("test_planner", [], temperature=0.0, max_tokens=500, response_format={"type": "json_object"})
    sent = json.loads(server.requests[0].content)
    assert sent["temperature"] == 0.0 and sent["max_tokens"] == 500
    assert sent["response_format"] == {"type": "json_object"}


def test_rate_limit_is_retried_using_the_servers_wait():
    server = FakeServer((429, {"error": "slow down"}, {"retry-after": "7"}), (200, answer()))
    c, waits = client(server)
    assert c.chat("test_planner", []).text == "{}"
    assert waits == [7.0]


def test_server_errors_back_off_then_give_up():
    server = FakeServer((503, {}), (502, {}), (500, {"oops": 1}))
    c, waits = client(server)
    with pytest.raises(OpenRouterError) as err:
        c.chat("test_planner", [])
    assert err.value.status == 500
    assert waits == [1.0, 2.0]
    assert len(server.requests) == 3


def test_network_drop_is_retried():
    server = FakeServer(httpx.ConnectError("no route"), (200, answer()))
    c, waits = client(server)
    assert c.chat("test_planner", []).text == "{}"
    assert waits == [1.0]


def test_our_own_mistakes_are_not_retried():
    server = FakeServer((401, {"error": "bad key"}))
    c, waits = client(server)
    with pytest.raises(OpenRouterError, match="401"):
        c.chat("test_planner", [])
    assert waits == [] and len(server.requests) == 1


def test_an_error_hidden_in_a_200_is_retried():
    server = FakeServer((200, {"error": {"message": "upstream overloaded"}}), (200, answer()))
    c, waits = client(server)
    assert c.chat("test_planner", []).text == "{}"
    assert len(waits) == 1


def test_cut_off_answers_are_marked():
    c, _ = client(FakeServer((200, answer('{"steps": [', finish="length"))))
    assert c.chat("test_planner", []).truncated


def test_a_broken_usage_log_does_not_lose_the_answer():
    def broken(**row):
        raise RuntimeError("db down")

    cfg = settings.load(ENV).llm
    c = OpenRouterClient(cfg, broken, http=httpx.Client(transport=httpx.MockTransport(FakeServer((200, answer())))))
    assert c.chat("test_planner", []).text == "{}"


def test_missing_key_or_model_is_a_clear_settings_error():
    with pytest.raises(settings.SettingsError, match="OPENROUTER_API_KEY"):
        client(FakeServer(), env={"OPENROUTER_API_KEY": ""})
    c, _ = client(FakeServer())
    with pytest.raises(settings.SettingsError, match="MODEL_CLAIM_READER"):
        c.chat("claim_reader", [])
    with pytest.raises(ValueError, match="unknown model role"):
        model_for(c.cfg, "poet")
