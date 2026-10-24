"""The OpenRouter client: one account that reaches every model.

- Calling code names a role ("test_planner"), never a model. The model comes from settings.
- Temperature defaults low, so the same project gets nearly the same answer on every run.
- Rate limits, server hiccups and network drops are retried with growing waits. Mistakes on
  our side (a bad key, a bad request) are not retried, because retrying won't fix them.
- Every successful call is logged with its model, time, tokens and cost.

The Azure Foundry client reuses all of this and only swaps the parts marked "provider details".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

import httpx

from talnex_ai.llm.models import model_for
from talnex_ai.settings import LLMSettings, SettingsError

log = logging.getLogger("talnex.llm")

# Worth another try: timeouts, conflicts, rate limits and server-side failures.
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 60.0

UsageLogger = Callable[..., Any]


class OpenRouterError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, retryable: bool = False,
                 wait: Optional[float] = None):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.wait = wait  # seconds the server asked us to wait before trying again, if it said


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    cost_usd: Optional[float]
    duration_ms: int
    # True when the model stopped because it hit max_tokens: the answer is cut off, and
    # cut-off JSON can't be parsed, so callers can raise the limit instead of guessing why.
    truncated: bool = False


class OpenRouterClient:
    service = "openrouter"
    label = "OpenRouter"
    error_class = OpenRouterError

    def __init__(
        self,
        cfg: LLMSettings,
        usage_logger: Optional[UsageLogger] = None,
        *,
        http: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        base_delay: float = 1.0,
    ):
        self.cfg = cfg
        self._check_settings()
        self.usage_logger = usage_logger
        self.http = http or httpx.Client(timeout=cfg.timeout_seconds)
        self.sleep = sleep
        self.base_delay = base_delay

    def chat(
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        job_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Mapping[str, Any]] = None,
    ) -> ChatResult:
        """Send one conversation to the model for `role` and return its answer."""
        model = self._model(role)
        body: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
            **self._extra_body(),
        }
        if response_format is not None:
            body["response_format"] = dict(response_format)

        started = time.monotonic()
        data = self._post_with_retries(body)
        result = self._read_answer(data, model, started)
        self._log_usage(result, job_id)
        return result

    # ---- provider details (the Azure client overrides these) ----

    def _check_settings(self) -> None:
        if not self.cfg.api_key:
            raise SettingsError("OPENROUTER_API_KEY is not set")

    def _model(self, role: str) -> str:
        return model_for(self.cfg, role)

    def _url(self) -> str:
        return f"{self.cfg.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json",
                "X-Title": "TalNex"}

    def _extra_body(self) -> dict[str, Any]:
        return {"usage": {"include": True}}  # ask OpenRouter to report what the call really cost

    def _cost(self, usage: Mapping[str, Any], tokens_in: Optional[int], tokens_out: Optional[int]) -> Optional[float]:
        cost = usage.get("cost")
        return float(cost) if cost is not None else None

    # ---- shared machinery ----

    def _post_with_retries(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        attempts = self.cfg.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._post_once(body)
            except OpenRouterError as err:
                if not err.retryable or attempt == attempts:
                    raise
                wait = err.wait or self._backoff(attempt)
                log.warning("%s call failed (try %d of %d), retrying in %.1fs: %s",
                            self.label, attempt, attempts, wait, err)
                self.sleep(wait)
        raise AssertionError("unreachable")

    def _post_once(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = self.http.post(self._url(), json=body, headers=self._headers())
        except httpx.TransportError as err:  # timeouts, refused connections, dropped sockets
            raise self.error_class(f"could not reach {self.label}: {err}", retryable=True) from err

        if response.status_code != 200:
            raise self.error_class(f"{self.label} answered {response.status_code}: {_snippet(response.text)}",
                                   status=response.status_code,
                                   retryable=response.status_code in RETRY_STATUS,
                                   wait=_retry_after(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise self.error_class(f"{self.label} sent a reply that is not JSON", retryable=True) from exc
        # Some upstream failures come back as 200 with an "error" object and no answer.
        if isinstance(data, dict) and data.get("error") and not data.get("choices"):
            raise self.error_class(f"{self.label} reported an error: {_snippet(str(data['error']))}", retryable=True)
        return data

    def _read_answer(self, data: Mapping[str, Any], model: str, started: float) -> ChatResult:
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise self.error_class(f"{self.label} reply was not in the expected shape: {exc!r}") from exc
        usage = data.get("usage") or {}
        tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        return ChatResult(
            text=text,
            model=data.get("model") or model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self._cost(usage, tokens_in, tokens_out),
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=choice.get("finish_reason") == "length",
        )

    def _log_usage(self, result: ChatResult, job_id: Optional[str]) -> None:
        if self.usage_logger is None:
            return
        try:
            self.usage_logger(service=self.service, model=result.model, job_id=job_id,
                              tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                              duration_ms=result.duration_ms, cost_usd=result.cost_usd)
        except Exception:  # the answer is already paid for; bookkeeping trouble must not lose it
            log.exception("could not write the usage log")

    def _backoff(self, attempt: int) -> float:
        return self.base_delay * (2 ** (attempt - 1))


def _retry_after(response: httpx.Response) -> Optional[float]:
    """The server's own "try again in N seconds", capped so one call can't stall a worker for long."""
    raw = response.headers.get("retry-after", "")
    try:
        return min(float(raw), MAX_RETRY_AFTER_SECONDS) if raw else None
    except ValueError:
        return None


def _snippet(text: str, limit: int = 200) -> str:
    return " ".join(text.split())[:limit]
