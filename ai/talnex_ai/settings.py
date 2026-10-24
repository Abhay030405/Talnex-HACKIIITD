"""Settings for the AI worker.

This is the only module that reads environment variables. Everything else is handed a
Settings object. If anything is missing or malformed, loading stops with one message that
lists every problem, so a bad .env is fixed in one go instead of one restart per mistake.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

# Every model call has a fixed role. Which model plays a role is chosen in .env, never in code.
MODEL_ROLES = {
    "video_reader": "MODEL_VIDEO_READER",
    "claim_reader": "MODEL_CLAIM_READER",
    "test_planner": "MODEL_TEST_PLANNER",
    "agent": "MODEL_AGENT",
    "proof_checker": "MODEL_PROOF_CHECKER",
    "opinion_a": "MODEL_OPINION_A",
    "opinion_b": "MODEL_OPINION_B",
    "copy_review": "MODEL_COPY_REVIEW",
}

PROVIDERS = ("openrouter", "azure_foundry")


class SettingsError(RuntimeError):
    """Raised when the environment is missing a required value or has a bad one."""


@dataclass(frozen=True)
class S3Settings:
    endpoint: str
    region: str
    bucket: str
    access_key: str
    secret_key: str


@dataclass(frozen=True)
class WorkerSettings:
    concurrency: int
    health_port: int
    poll_seconds: int
    retry_delay_seconds: int


@dataclass(frozen=True)
class AzureFoundrySettings:
    """One Azure deployment that answers every model role. Only used when LLM_PROVIDER=azure_foundry."""

    endpoint: str = ""
    api_key: str = ""
    model: str = ""
    # Azure doesn't report cost, so we work it out from these prices (dollars per million tokens).
    price_in_per_m: Optional[float] = None
    price_out_per_m: Optional[float] = None


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str
    temperature: float
    max_retries: int
    timeout_seconds: float
    # Sent on every call without its own cap. Without it OpenRouter reserves the model's full
    # output size and can refuse the call when the balance is low.
    max_tokens: int = 16384
    models: Mapping[str, str] = field(default_factory=dict)
    provider: str = "openrouter"
    azure: AzureFoundrySettings = field(default_factory=AzureFoundrySettings)


@dataclass(frozen=True)
class LimitSettings:
    """Hard caps that keep testing a live site polite and cheap."""

    max_tries_per_claim: int
    max_agent_runs_per_project: int
    sleeping_host_wait_seconds: int
    extra_tests_per_claim: int = 1


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3: S3Settings
    worker: WorkerSettings
    llm: LLMSettings
    limits: LimitSettings


class _Env:
    """Reads typed values from the environment and collects problems instead of failing on the first."""

    def __init__(self, source: Mapping[str, str]):
        self._source = source
        self.problems: list[str] = []

    def _raw(self, name: str) -> str:
        return self._source.get(name, "").strip()

    def required(self, name: str) -> str:
        value = self._raw(name)
        if not value:
            self.problems.append(f"{name} is missing")
        return value

    def optional(self, name: str, default: str = "") -> str:
        return self._raw(name) or default

    def url(self, name: str, required: bool = True) -> str:
        value = self.required(name) if required else self.optional(name)
        return value.rstrip("/")

    def whole(self, name: str, default: int) -> int:
        raw = self._raw(name)
        if not raw:
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        self.problems.append(f"{name} must be a positive whole number (got {raw!r})")
        return default

    def decimal(self, name: str, default: float, low: float, high: float) -> float:
        value = self.decimal_or_none(name, low, high)
        return default if value is None else value

    def decimal_or_none(self, name: str, low: float, high: float) -> Optional[float]:
        raw = self._raw(name)
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            value = None
        if value is None or not low <= value <= high:
            self.problems.append(f"{name} must be a number between {low:g} and {high:g} (got {raw!r})")
            return None
        return value

    def one_of(self, name: str, default: str, options: tuple[str, ...]) -> str:
        value = self._raw(name).lower() or default
        if value not in options:
            self.problems.append(f"{name} must be one of {', '.join(options)} (got {value!r})")
            return default
        return value

    def stop_if_bad(self) -> None:
        if self.problems:
            raise SettingsError("Bad settings, see .env.example:\n  - " + "\n  - ".join(self.problems))


def load(source: Optional[Mapping[str, str]] = None) -> Settings:
    """Build Settings from the environment (or from `source`, which tests use)."""
    env = _Env(os.environ if source is None else source)

    s3 = S3Settings(
        endpoint=env.url("S3_ENDPOINT"),
        region=env.required("S3_REGION"),
        bucket=env.required("S3_BUCKET"),
        access_key=env.required("S3_ACCESS_KEY"),
        secret_key=env.required("S3_SECRET_KEY"),
    )
    worker = WorkerSettings(
        concurrency=env.whole("AI_WORKER_CONCURRENCY", 5),
        health_port=env.whole("AI_WORKER_HEALTH_PORT", 8082),
        poll_seconds=env.whole("JOB_POLL_SECONDS", 5),
        retry_delay_seconds=env.whole("JOB_RETRY_DELAY_SECONDS", 30),
    )
    # Keys and model names are optional here: a worker that never calls a model (the self-test)
    # must still start. The model client checks them when a call is actually made.
    llm = LLMSettings(
        api_key=env.optional("OPENROUTER_API_KEY"),
        base_url=env.url("OPENROUTER_BASE_URL"),
        temperature=env.decimal("LLM_TEMPERATURE", 0.1, 0.0, 2.0),
        max_retries=env.whole("OPENROUTER_MAX_RETRIES", 3),
        timeout_seconds=float(env.whole("OPENROUTER_TIMEOUT_SECONDS", 120)),
        max_tokens=env.whole("OPENROUTER_MAX_TOKENS", 16384),
        models={role: env.optional(var) for role, var in MODEL_ROLES.items()},
        provider=env.one_of("LLM_PROVIDER", "openrouter", PROVIDERS),
        azure=AzureFoundrySettings(
            endpoint=env.url("AZURE_FOUNDRY_ENDPOINT", required=False),
            api_key=env.optional("AZURE_FOUNDRY_API_KEY"),
            model=env.optional("AZURE_FOUNDRY_MODEL"),
            price_in_per_m=env.decimal_or_none("AZURE_FOUNDRY_PRICE_IN_PER_M", 0.0, 10_000.0),
            price_out_per_m=env.decimal_or_none("AZURE_FOUNDRY_PRICE_OUT_PER_M", 0.0, 10_000.0),
        ),
    )
    limits = LimitSettings(
        max_tries_per_claim=env.whole("MAX_TRIES_PER_CLAIM", 3),
        max_agent_runs_per_project=env.whole("MAX_AGENT_RUNS_PER_PROJECT", 30),
        sleeping_host_wait_seconds=env.whole("SLEEPING_HOST_WAIT_SECONDS", 60),
        extra_tests_per_claim=env.whole("EXTRA_TESTS_PER_CLAIM", 1),
    )
    database_url = env.required("DATABASE_URL")

    env.stop_if_bad()
    return Settings(database_url=database_url, s3=s3, worker=worker, llm=llm, limits=limits)
