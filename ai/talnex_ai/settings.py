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
class TinyFishKey:
    label: str  # a short name used in logs and the usage log, never the key itself
    key: str


@dataclass(frozen=True)
class TinyFishSettings:
    """TinyFish: one or more API keys (each account has its own credit), addresses, prices and the spending limit."""

    keys: tuple[TinyFishKey, ...]
    agent_base_url: str
    browser_base_url: str
    fetch_base_url: str
    session_timeout_seconds: int
    parallel_runs: int
    budget_usd: float           # credit we may use per key
    reserve_usd: float          # kept back per key: paid calls stop before touching it
    agent_step_usd: float
    browser_minute_usd: float
    search_base_url: str = ""   # empty means web search is off, and checks that need it say so


@dataclass(frozen=True)
class RunnerSettings:
    """Caps on one browser test run, so a confused model can't wander off or keep a session billing."""

    max_actions: int
    max_actions_per_step: int
    max_seconds: int
    snapshot_chars: int
    uploads_dir: str  # the only folder the agent may upload test files from (known-answer photos, the test resume)


@dataclass(frozen=True)
class EmailSettings:
    """The one AgentMail inbox used for every sign-up on tested sites (login ladder, step 3).
    `login_secret` makes the throwaway sign-up passwords; without it, email sign-up is off."""

    api_key: str
    base_url: str
    inbox: str
    wait_seconds: int
    poll_seconds: int
    login_secret: str


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3: S3Settings
    worker: WorkerSettings
    llm: LLMSettings
    limits: LimitSettings
    tinyfish: TinyFishSettings
    runner: RunnerSettings
    email: EmailSettings


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


def parse_tinyfish_keys(pool: str, single: str = "") -> tuple[TinyFishKey, ...]:
    """Read TINYFISH_API_KEYS: a comma-separated list of `label=key` or bare `key` entries (bare ones are
    labelled k1, k2, ...). Falls back to TINYFISH_API_KEY. No key at all is allowed: only calls that
    actually need TinyFish will fail."""
    keys = []
    for number, entry in enumerate((e.strip() for e in pool.split(",") if e.strip()), start=1):
        label, sep, key = entry.partition("=")
        label, key = (label.strip(), key.strip()) if sep else (f"k{number}", entry)
        if not label or not key or not all(c.isalnum() or c == "-" for c in label):
            raise SettingsError(f"TINYFISH_API_KEYS entry {number} needs a label of letters, digits or dashes, and a key")
        keys.append(TinyFishKey(label, key))
    if not keys and single.strip():
        keys.append(TinyFishKey("main", single.strip()))
    labels = [k.label for k in keys]
    if len(set(labels)) != len(labels):
        raise SettingsError("TINYFISH_API_KEYS uses the same label twice")
    return tuple(keys)


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
    try:
        tinyfish_keys = parse_tinyfish_keys(env.optional("TINYFISH_API_KEYS"), env.optional("TINYFISH_API_KEY"))
    except SettingsError as err:
        env.problems.append(str(err))
        tinyfish_keys = ()
    tinyfish = TinyFishSettings(
        keys=tinyfish_keys,
        agent_base_url=env.url("TINYFISH_AGENT_BASE_URL"),
        browser_base_url=env.url("TINYFISH_BROWSER_BASE_URL"),
        fetch_base_url=env.url("TINYFISH_FETCH_BASE_URL"),
        session_timeout_seconds=env.whole("TINYFISH_SESSION_TIMEOUT_SECONDS", 300),
        parallel_runs=env.whole("TINYFISH_PARALLEL_RUNS", 5),
        budget_usd=env.decimal("TINYFISH_BUDGET_USD", 10.0, 0.0, 100_000.0),
        reserve_usd=env.decimal("TINYFISH_BUDGET_RESERVE_USD", 2.0, 0.0, 100_000.0),
        agent_step_usd=env.decimal("TINYFISH_AGENT_STEP_USD", 0.016, 0.0, 10.0),
        browser_minute_usd=env.decimal("TINYFISH_BROWSER_MINUTE_USD", 0.002, 0.0, 10.0),
        search_base_url=env.url("TINYFISH_SEARCH_BASE_URL", required=False),
    )
    runner = RunnerSettings(
        max_actions=env.whole("RUNNER_MAX_ACTIONS", 40),
        max_actions_per_step=env.whole("RUNNER_MAX_ACTIONS_PER_STEP", 6),
        max_seconds=env.whole("RUNNER_MAX_SECONDS", 240),
        snapshot_chars=env.whole("RUNNER_SNAPSHOT_CHARS", 6000),
        uploads_dir=env.optional("TEST_FILES_DIR", "testdata"),
    )
    email = EmailSettings(
        api_key=env.optional("AGENTMAIL_API_KEY"),
        base_url=env.url("AGENTMAIL_BASE_URL"),
        inbox=env.optional("AGENTMAIL_INBOX"),
        wait_seconds=env.whole("AGENTMAIL_WAIT_SECONDS", 90),
        poll_seconds=env.whole("AGENTMAIL_POLL_SECONDS", 3),
        login_secret=env.optional("EMAIL_LOGIN_SECRET"),
    )
    database_url = env.required("DATABASE_URL")

    env.stop_if_bad()
    return Settings(database_url=database_url, s3=s3, worker=worker, llm=llm, limits=limits, tinyfish=tinyfish,
                    runner=runner, email=email)
