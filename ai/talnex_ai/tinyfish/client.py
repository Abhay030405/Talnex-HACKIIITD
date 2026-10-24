"""All TinyFish calls: Fetch and Search (free), and remote browser sessions we drive ourselves.

What the phase 1 spike measured (docs/phase1/02_tinyfish_findings.md):
- A Browser API session costs about $0.002 a minute: over 100 times cheaper than the Agent API
  for the same task, so the test runner drives the browser itself with Playwright.
- Fetch is free and gives a clear error code per address, which is exactly what the
  never-blame ladder's "did the page load?" step needs.
- A session is billed while it exists, so every session is ended in close(), and each one also
  has a short inactivity timeout in case this process dies.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

import httpx

from talnex_ai.settings import TinyFishKey, TinyFishSettings
from talnex_ai.tinyfish.budget import Budget

log = logging.getLogger("talnex.tinyfish")

FETCH_BATCH = 10  # Fetch takes at most 10 addresses per request
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class TinyFishError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class FetchResult:
    url: str
    ok: bool
    final_url: Optional[str] = None
    title: Optional[str] = None
    text: str = ""
    error_code: Optional[str] = None  # page_not_found, invalid_url, timeout, ...
    http_status: Optional[int] = None


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


class BrowserSession:
    """A remote browser. Connect Playwright to `cdp_url`. Use it in a `with` block, or call close()."""

    def __init__(self, client: "TinyFishClient", key: TinyFishKey, session_id: str, cdp_url: str,
                 base_url: str, requested_at: float, job_id: Optional[str]):
        self._client = client
        self._key = key
        self.session_id = session_id
        self.cdp_url = cdp_url
        self.base_url = base_url
        self._requested_at = requested_at  # billing starts about when the session was asked for
        self._job_id = job_id
        self.closed = False
        self.cost_usd: Optional[float] = None

    @property
    def account(self) -> str:
        return self._key.label

    def close(self) -> float:
        """End the session and record its cost. Safe to call twice. Returns the estimated cost in dollars."""
        if self.closed:
            return self.cost_usd or 0.0
        self.closed = True
        try:
            self._client._end_session(self._key, self.session_id)
        except Exception as err:  # it still ends by itself at its inactivity timeout
            log.warning("could not end TinyFish session %s (it will time out on its own): %s", self.session_id, err)
        seconds = max(self._client._clock() - self._requested_at, 0.0)
        self.cost_usd = round(seconds / 60.0 * self._client.cfg.browser_minute_usd, 6)
        if self._client.budget is not None:
            self._client.budget.record(self._key.label, "browser", self.cost_usd, int(seconds * 1000), self._job_id)
        return self.cost_usd

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class TinyFishClient:
    def __init__(
        self,
        cfg: TinyFishSettings,
        budget: Optional[Budget] = None,
        *,
        http: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 2,
    ):
        self.cfg = cfg
        self.budget = budget
        self.http = http or httpx.Client(timeout=120)
        self._sleep = sleep
        self._clock = clock
        self._max_retries = max_retries

    # ---- Fetch (free) ----

    def fetch(self, urls: Sequence[str], *, fresh: bool = True, fmt: str = "markdown") -> list[FetchResult]:
        """Load and read addresses. Returns one result per address, in the same order.

        A dead page is never an exception: it's a result with ok=False and an error code."""
        key = self._any_key()
        found: dict[str, FetchResult] = {}
        for start in range(0, len(urls), FETCH_BATCH):
            body: dict[str, Any] = {"urls": list(urls[start:start + FETCH_BATCH]), "format": fmt}
            if fresh:
                body["ttl"] = 0  # don't serve a cached copy: we want to know if it's alive now
            data = self._request("POST", self.cfg.fetch_base_url, key, json=body)
            for item in data.get("results") or []:
                found[_same_page(item.get("url", ""))] = FetchResult(
                    url=item.get("url", ""), ok=True, final_url=item.get("final_url"),
                    title=item.get("title"), text=item.get("text") or "")
            for item in data.get("errors") or []:
                found[_same_page(item.get("url", ""))] = FetchResult(
                    url=item.get("url", ""), ok=False, error_code=item.get("error") or "unknown",
                    http_status=item.get("status"))
        results = []
        for url in urls:
            hit = found.get(_same_page(url))
            # Report under the address we were given, even if TinyFish wrote it slightly differently.
            results.append(_with_url(hit, url) if hit else FetchResult(url=url, ok=False, error_code="no_result"))
        return results

    # ---- Search (free) ----

    def search(self, query: str, *, limit: int = 8) -> list[SearchHit]:
        """Web search. Raises TinyFishError when search is off or fails; callers treat that as "could not check"."""
        if not self.cfg.search_base_url:
            raise TinyFishError("web search is off (set TINYFISH_SEARCH_BASE_URL)")
        data = self._request("GET", self.cfg.search_base_url, self._any_key(), params={"query": query}, timeout=30)
        items = data.get("results") if isinstance(data, dict) else None
        hits = []
        for item in (items or [])[:limit]:
            if isinstance(item, dict) and item.get("url"):
                hits.append(SearchHit(str(item.get("title") or ""), str(item["url"]), str(item.get("snippet") or "")))
        return hits

    # ---- Browser sessions (paid by the minute) ----

    def open_session(self, url: Optional[str] = None, *, timeout_seconds: Optional[int] = None,
                     job_id: Optional[str] = None) -> BrowserSession:
        """Start a remote browser. The budget must cover at least one minute first."""
        key = self.budget.pick(self.cfg.browser_minute_usd) if self.budget is not None else self._any_key()
        body: dict[str, Any] = {"timeout_seconds": timeout_seconds or self.cfg.session_timeout_seconds}
        if url:
            body["url"] = url
        requested_at = self._clock()
        data = self._request("POST", self.cfg.browser_base_url, key, json=body, expect=(200, 201))
        try:
            return BrowserSession(self, key, data["session_id"], data["cdp_url"], data.get("base_url", ""),
                                  requested_at, job_id)
        except KeyError as err:
            raise TinyFishError(f"TinyFish session reply is missing {err}") from err

    def _end_session(self, key: TinyFishKey, session_id: str) -> None:
        response = self.http.delete(f"{self.cfg.browser_base_url}/{session_id}", headers=_headers(key), timeout=30)
        if response.status_code not in (200, 202, 204, 404):  # 404: it had already ended
            raise TinyFishError(f"ending the session answered {response.status_code}", response.status_code)

    # ---- plumbing ----

    def _any_key(self) -> TinyFishKey:
        if not self.cfg.keys:
            raise TinyFishError("no TinyFish key is configured (set TINYFISH_API_KEY or TINYFISH_API_KEYS)")
        return self.cfg.keys[0]

    def _request(self, method: str, url: str, key: TinyFishKey, *, json: Optional[dict] = None,
                 params: Optional[dict] = None, expect: tuple[int, ...] = (200,),
                 timeout: Optional[float] = None) -> Any:
        """One call with retries for timeouts, rate limits and server errors. A refused key is never retried."""
        options: dict[str, Any] = {"headers": _headers(key), "json": json, "params": params}
        if timeout is not None:
            options["timeout"] = timeout
        for attempt in range(1, self._max_retries + 2):
            try:
                response = self.http.request(method, url, **options)
            except httpx.TransportError as err:
                error = TinyFishError(f"could not reach TinyFish: {err}")
            else:
                if response.status_code in expect:
                    try:
                        return response.json()
                    except ValueError as err:
                        raise TinyFishError("TinyFish answered with something that is not JSON") from err
                message = _error_message(response)
                if response.status_code in (401, 403):
                    raise TinyFishError(f"TinyFish refused the key ({response.status_code}): {message}",
                                        response.status_code)
                error = TinyFishError(f"TinyFish answered {response.status_code}: {message}", response.status_code)
                if response.status_code not in RETRY_STATUS:
                    raise error
            if attempt > self._max_retries:
                raise error
            self._sleep(2.0 * attempt)
        raise AssertionError("unreachable")


def _headers(key: TinyFishKey) -> dict[str, str]:
    return {"X-API-Key": key.key, "Content-Type": "application/json", "User-Agent": "talnex"}


def _same_page(url: str) -> str:
    """A matching key that ignores differences TinyFish may introduce: case of the host and a trailing slash."""
    url = url.strip()
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url.rstrip("/")
    host, slash, path = rest.partition("/")
    return f"{scheme.lower()}://{host.lower()}{slash}{path}".rstrip("/")


def _with_url(result: FetchResult, url: str) -> FetchResult:
    return FetchResult(url=url, ok=result.ok, final_url=result.final_url, title=result.title, text=result.text,
                       error_code=result.error_code, http_status=result.http_status)


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:200]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or error)[:200]
    return str(error or data)[:200]
