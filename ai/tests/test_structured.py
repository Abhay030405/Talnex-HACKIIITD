import base64
from dataclasses import dataclass
from functools import partial

import pytest

from talnex_ai.formats import TestPlan, parse_model
from talnex_ai.llm.structured import JSON_MODE, StructuredError, ask_json, image_type, user_message

GOOD = '{"test_type": "normal", "steps": [{"action": "open the page", "expected": "a form"}], "expected_result": "done"}'
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8


@dataclass
class Reply:
    text: str
    truncated: bool = False


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, role, messages, **options):
        self.calls.append({"role": role, "messages": list(messages), **options})
        reply = self.replies.pop(0)
        return reply if isinstance(reply, Reply) else Reply(reply)


parse_plan = partial(parse_model, TestPlan)


def test_a_good_answer_needs_one_call():
    client = FakeClient(GOOD)
    plan = ask_json(client, "test_planner", "be careful", "plan it", parse_plan, job_id="j1", temperature=0)
    assert plan.steps[0].action == "open the page"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["response_format"] == JSON_MODE and call["job_id"] == "j1" and call["temperature"] == 0
    assert call["messages"][0] == {"role": "system", "content": "be careful"}
    assert "max_tokens" not in call


def test_a_bad_answer_gets_one_repair_that_shows_the_mistake():
    client = FakeClient('{"test_type": "normal", "steps": []}', GOOD)
    assert ask_json(client, "test_planner", "s", "u", parse_plan).test_type == "normal"
    repair = client.calls[1]["messages"]
    assert repair[-2] == {"role": "assistant", "content": '{"test_type": "normal", "steps": []}'}
    assert "not valid" in repair[-1]["content"] and "steps" in repair[-1]["content"]


def test_two_bad_answers_fail_clearly():
    client = FakeClient("no idea", "still no idea")
    with pytest.raises(StructuredError, match="test_planner"):
        ask_json(client, "test_planner", "s", "u", parse_plan)
    assert len(client.calls) == 2


def test_a_cut_off_answer_is_retried_with_more_room():
    client = FakeClient(Reply('{"test_type": "normal", "steps": [', truncated=True), GOOD)
    ask_json(client, "test_planner", "s", "u", parse_plan, max_tokens=1000)
    assert client.calls[0]["max_tokens"] == 1000 and client.calls[1]["max_tokens"] == 2000
    assert "cut off" in client.calls[1]["messages"][-1]["content"]


def test_other_errors_are_not_swallowed():
    def parse(text):
        raise KeyError("a bug in our parser")

    with pytest.raises(KeyError):
        ask_json(FakeClient(GOOD), "test_planner", "s", "u", parse)


def test_screenshots_are_attached_with_the_right_type():
    message = user_message("is the cart full?", [PNG, JPEG])
    assert message["content"][0] == {"type": "text", "text": "is the cart full?"}
    urls = [part["image_url"]["url"] for part in message["content"][1:]]
    assert urls[0] == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert urls[1].startswith("data:image/jpeg;base64,")
    assert user_message("plain") == {"role": "user", "content": "plain"}


def test_unknown_image_bytes_are_refused():
    assert image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    with pytest.raises(ValueError, match="unsupported image"):
        image_type(b"%PDF-1.7")
