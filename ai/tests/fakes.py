"""Scripted stand-ins for the model, the browser, the file store and TinyFish, shared by the runner tests."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Optional

from talnex_ai.testing.runner.driver import ActionError
from talnex_ai.tinyfish.client import FetchResult

LONG_PAGE = '- heading "Welcome"\n- textbox "Search"\n- button "Add"\n- list:\n  - listitem: first item\n' * 3


class Reply:
    def __init__(self, text: str, truncated: bool = False):
        self.text = text
        self.truncated = truncated


class ScriptedModel:
    """Answers with a scripted list of replies, in order, and remembers every request."""

    def __init__(self, *replies: Any):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.calls: list[dict] = []

    def chat(self, role, messages, **options):
        self.calls.append({"role": role, "messages": list(messages), **options})
        if not self.replies:
            raise AssertionError("the model was asked more times than the test expected")
        return Reply(self.replies.pop(0))

    def user_text(self, n: int) -> str:
        content = self.calls[n]["messages"][1]["content"]
        return content if isinstance(content, str) else content[0]["text"]

    def had_picture(self, n: int) -> bool:
        return not isinstance(self.calls[n]["messages"][1]["content"], str)


def act(**action) -> dict:
    return {"thought": "next", "action": action}


def done(observed="it worked") -> dict:
    return {"thought": "finished", "step_result": "done", "observed": observed}


def verdict(v="works", observed="the result is visible") -> dict:
    return {"verdict": v, "observed": observed}


class FakeDriver:
    """A pretend page. Each successful action moves it to the next scripted page state."""

    def __init__(self, snapshots: Optional[list[str]] = None, *, url="https://demo.example.com/",
                 fail: frozenset = frozenset(), hidden: Optional[list[str]] = None):
        self.snapshots = snapshots or [LONG_PAGE]
        self.position = 0
        self.fail = set(fail)
        self.hidden = hidden or []
        self.performed: list[Any] = []
        self.attempts = 0
        self.shots = 0
        self._url = url

    def url(self) -> str:
        return self._url

    def title(self) -> str:
        return "Demo"

    def snapshot(self) -> str:
        return self.snapshots[min(self.position, len(self.snapshots) - 1)]

    def screenshot(self) -> bytes:
        self.shots += 1
        return b"\xff\xd8\xff" + f"jpeg-{self.shots}".encode()  # starts like a real JPEG

    def hidden_text(self) -> list[str]:
        return list(self.hidden)

    def perform(self, action, uploads_root) -> None:
        self.attempts += 1
        if self.attempts in self.fail:
            raise ActionError("element not found")
        self.performed.append(action)
        self.position += 1


class FakeFiles:
    """Stands in for the S3 store."""

    def __init__(self, fail: bool = False):
        self.saved: dict[str, bytes] = {}
        self.fail = fail

    def put_bytes(self, key: str, data: bytes, content_type: str = "") -> None:
        if self.fail:
            raise RuntimeError("storage down")
        self.saved[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.saved[key]


class FakeSession:
    def __init__(self, account="main"):
        self.account = account
        self.cdp_url = "wss://fake/cdp"
        self.closed = False
        self.cost_usd: Optional[float] = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        self.cost_usd = 0.0005


class FakeTinyFish:
    def __init__(self, error: Optional[Exception] = None, dead: Optional[dict] = None):
        self.error = error
        self.dead = dead or {}  # url -> error code, for pages that don't load
        self.sessions: list[FakeSession] = []
        self.fetched: list[str] = []

    def fetch(self, urls, **_):
        results = []
        for u in urls:
            self.fetched.append(u)
            if u in self.dead:
                results.append(FetchResult(url=u, ok=False, error_code=self.dead[u], http_status=404))
            else:
                results.append(FetchResult(url=u, ok=True, final_url=u, title="Demo", text="A normal page"))
        return results

    def open_session(self, url=None, job_id=None, **_):
        if self.error:
            raise self.error
        session = FakeSession()
        self.sessions.append(session)
        return session


def connector(driver, boom: Optional[Exception] = None):
    @contextmanager
    def connect(cdp_url: str):
        if boom:
            raise boom
        yield driver

    return connect
