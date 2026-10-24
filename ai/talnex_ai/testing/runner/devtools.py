"""What the browser's developer tools see during a live test, collected step by step.

The driver feeds browser events in; `drain()` hands back what happened since the last step and starts over. Watched
only: nothing extra is ever sent to the site. URLs lose their query strings (they can hold tokens). The result is
evidence for the step, never a verdict on its own: an error answer in the background is not proof a feature is broken.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from talnex_ai.safety.leaks import scan

SLOW_MS = 2000          # an API call slower than this is noted as slow
MAX_ITEMS = 15          # per list, so a chatty page cannot bloat a step record
MAX_TEXT = 200
API_TYPES = ("fetch", "xhr")


def bare_url(url: str) -> str:
    """The address without its query string or fragment."""
    try:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))[:MAX_TEXT]
    except ValueError:
        return url.split("?", 1)[0][:MAX_TEXT]


class DevtoolsWatch:
    """Collects browser events between two `drain()` calls."""

    def __init__(self) -> None:
        self._pending: dict[int, dict] = {}
        self._reset()

    def _reset(self) -> None:
        self.api: list[dict] = []
        self.errors: list[dict] = []
        self.failed: list[dict] = []
        self.console: list[str] = []
        self.crashes: list[str] = []
        self.leaks: list[dict] = []

    @staticmethod
    def _add(items: list, item) -> None:
        if len(items) < MAX_ITEMS:
            items.append(item)

    def response(self, key: int, method: str, url: str, status: int, resource_type: str) -> None:
        call = {"method": method, "url": bare_url(url), "status": status, "type": resource_type}
        self._pending[key] = call
        if status >= 400:
            self._add(self.errors, call)

    def finished(self, key: int, elapsed_ms: Optional[float]) -> None:
        """A request completed; `elapsed_ms` is from sending it to the end of the answer."""
        call = self._pending.pop(key, None)
        if call is None:
            return
        if elapsed_ms is not None and elapsed_ms >= 0:
            call["ms"] = round(elapsed_ms)
        if call["type"] in API_TYPES:
            self._add(self.api, call)

    def failed_request(self, method: str, url: str, error: str) -> None:
        self._add(self.failed, {"method": method, "url": bare_url(url), "error": (error or "")[:MAX_TEXT]})

    def console_message(self, kind: str, text: str) -> None:
        if kind in ("error", "warning"):
            self._add(self.console, f"[{kind}] {text[:MAX_TEXT]}")
        self.found_leaks("console", scan(text[:20000]))

    def found_leaks(self, where: str, findings: list[dict]) -> None:
        """Masked leaks (safety/leaks): the secret itself never reaches the step record."""
        for f in findings:
            self._add(self.leaks, {**f, "where": where[:MAX_TEXT]})

    def page_error(self, text: str) -> None:
        self._add(self.crashes, text[:MAX_TEXT])

    def drain(self) -> Optional[dict]:
        """What happened since the last call, or None when there was nothing to note.
        A request still in flight stays pending and belongs to the next step."""
        out = {
            "api_calls": self.api, "error_responses": self.errors, "failed_requests": self.failed,
            "console_errors": self.console, "page_errors": self.crashes, "leaks": self.leaks,
            "slow_api_calls": sum(1 for c in self.api if c.get("ms", 0) >= SLOW_MS),
        }
        self._reset()
        return out if any(out.values()) else None
