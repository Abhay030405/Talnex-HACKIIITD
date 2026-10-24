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
    "tour_guide": "MODEL_TOUR_GUIDE",
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
    uploads_dir: str
    seconds_per_step: int = 60  # a longer plan gets more time: the limit is the larger of max_seconds and this per step
    model_free_steps: bool = True  # steps that name one clear action are done by plain code, with no model call


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
class PhoneSettings:
    """The team SIM for the phone way in (login ladder). Texts reach us through the API (the
    `inbound_sms` table). An empty number means phone sign-up is off."""

    number: str
    wait_seconds: int
    poll_seconds: int

    @property
    def enabled(self) -> bool:
        return bool(self.number)


@dataclass(frozen=True)
class SandboxSettings:
    """The VM host that runs repos (sandboxd). Without an address or token the sandbox track is simply off:
    a repo then ends as "could not run: the sandbox host is not set up", never as a problem with the project."""

    url: str
    token: str
    vm_time_limit_seconds: int      # how long one VM may live
    build_timeout_seconds: int      # the longest one command (install, build, test run) may take
    busy_wait_seconds: int          # how long to wait for a free place when the host is full
    review_max_files: int = 12      # source files read for the code review of one claim
    review_max_kb: int = 120        # the most code, in kilobytes, read for one claim
    feature_read_max_files: int = 25   # files read to find the features a project implements
    feature_read_max_kb: int = 200     # the most code, in kilobytes, read for that
    feature_max_claims: int = 12       # the most features turned into claims

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)


@dataclass(frozen=True)
class CopySettings:
    """The copy check between teams."""

    review_pct: float = 40.0     # this much shared code (of the smaller team's own) is a "review" flag
    strong_pct: float = 70.0     # and this much is a "strong" flag
    starter_share: float = 0.5   # code found in at least this share of teams (and 3 teams) is starter code, ignored
    max_teams: int = 60          # the most teams read in one event
    look_max_files: int = 3      # the model looks at this many top matching files of a pair


@dataclass(frozen=True)
class AuthorshipSettings:
    """Authorship proof: how much code is read to find a feature, and the flag thresholds (starting values)."""

    locate_max_files: int = 40        # code files read to find where the claims live, however big the repo
    max_claims: int = 25              # the most claims traced in one project
    max_files_per_claim: int = 6      # the most files in one claim's code map
    min_confidence: float = 0.6       # a code map less sure than this: "could not trace: code not found"
    top_commits: int = 8              # commits shown to the model that decides new / moved / reformatting
    one_drop_share: float = 0.8       # this share of a feature's lines in one commit: "arrived in one drop"
    before_event_review: float = 0.3  # more than this share pushed before the event: review
    before_event_strong: float = 0.6  # more than this, on a main feature: strong
    claimed_min_share: float = 0.2    # "I built" with less than this share by the candidate's account: review
    reformat_share: float = 0.5       # more than this share owned by reformatting commits: info


@dataclass(frozen=True)
class WalkthroughSettings:
    """The voice walkthrough: how much code one answer reads, and the speech-to-text model."""

    max_files: int = 8              # code files read for one answer
    max_lines_per_file: int = 120   # lines read from one file's traced range
    snippet_lines: int = 20         # lines shown with one code proof link
    whisper_model: str = "small"    # faster-whisper size: tiny, base, small, medium, large-v3
    whisper_device: str = "cpu"     # cpu or cuda
    whisper_compute_type: str = "int8"


@dataclass(frozen=True)
class LeetCodeReplaySettings:
    """The LeetCode Code Replay paste check (architecture section 18): which contests, and when a paste is suspicious."""

    contests: int = 5               # most recent rated contests read (plus any with a rating jump)
    rating_jump: int = 100          # a contest whose rating gain is at least this is also read
    settle_days: int = 7            # newer contests are skipped until LeetCode's own checks have settled
    paste_min_lines: int = 4        # shorter pastes are helper code, never suspicious
    template_seconds: int = 60      # a paste this soon after opening the problem is a personal template
    max_edits_after: int = 3        # a core paste with at most this many edits after it is "pasted in one go"
    repeat_contests: int = 3        # suspicious pastes in this many contests make every one of them strong
    match_min_lines: int = 12       # a Medium paste at least this long is compared with nearby contestants' code
    match_pages: int = 5            # ranking pages read on each side of the candidate's own (25 people a page)
    match_pct: float = 90.0         # how much of the paste must be in someone else's code to count as the same
    match_min_users: int = 2        # this many matching people make the paste strong


@dataclass(frozen=True)
class TourSettings:
    """The guided tour (architecture section 32): the guide reads code in a read-only VM, the driver shows it live."""

    max_browser_steps: int = 12     # browser actions in one tour message
    vm_minutes: int = 30            # how long a chat's code VM lives before the host's reaper removes it
    guide_max_tool_calls: int = 12  # list, search and read calls the guide may make before it must write the tour
    repo_max_mb: int = 30           # the biggest repository download accepted
    file_max_kb: int = 200          # a bigger code file is left out of the VM
    max_files: int = 3000           # most files put in the VM


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
    phone: PhoneSettings = field(default_factory=lambda: PhoneSettings("", 90, 3))
    sandbox: SandboxSettings = field(default_factory=lambda: SandboxSettings("", "", 900, 600, 600))
    copy: CopySettings = field(default_factory=CopySettings)
    authorship: AuthorshipSettings = field(default_factory=AuthorshipSettings)
    walkthrough: WalkthroughSettings = field(default_factory=WalkthroughSettings)
    leetcode_replay: LeetCodeReplaySettings = field(default_factory=LeetCodeReplaySettings)
    # The candidate report waits this long for the coding profile checks before it is built without them
    report_coding_wait_seconds: int = 480
    tour: TourSettings = field(default_factory=TourSettings)
    # LeetCode's public data address (the one its profile pages read, no login). Empty: read the profile page instead.
    leetcode_graphql_url: str = ""
    # A Chrome-over-CDP endpoint used as a backup browser when TinyFish is unavailable. Hosted Browserless /stealth also
    # solves CAPTCHAs during the test; a self-hosted container cannot. Empty: off.
    browserless_cdp_url: str = ""
    browserless_token: str = ""
    # Browserless BQL endpoint (hosted /stealth/bql) for the team LinkedIn login. Empty: LinkedIn checks are off.
    browserless_bql_url: str = ""
    linkedin_email: str = ""
    linkedin_password: str = ""


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
        seconds_per_step=env.whole("RUNNER_SECONDS_PER_STEP", 60),
        snapshot_chars=env.whole("RUNNER_SNAPSHOT_CHARS", 6000),
        model_free_steps=env.one_of("RUNNER_MODEL_FREE_STEPS", "1", ("0", "1")) == "1",
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
    phone = PhoneSettings(
        number=env.optional("TEAM_PHONE_NUMBER"),
        wait_seconds=env.whole("SMS_WAIT_SECONDS", 90),
        poll_seconds=env.whole("SMS_POLL_SECONDS", 3),
    )
    sandbox = SandboxSettings(
        url=env.url("SANDBOXD_URL", required=False),
        token=env.optional("SANDBOXD_TOKEN"),
        vm_time_limit_seconds=env.whole("SANDBOX_VM_TIME_LIMIT_SECONDS", 900),
        build_timeout_seconds=env.whole("SANDBOX_BUILD_TIMEOUT_SECONDS", 600),
        busy_wait_seconds=env.whole("SANDBOX_BUSY_WAIT_SECONDS", 600),
        review_max_files=env.whole("SANDBOX_REVIEW_MAX_FILES", 12),
        review_max_kb=env.whole("SANDBOX_REVIEW_MAX_KB", 120),
        feature_read_max_files=env.whole("FEATURE_READ_MAX_FILES", 25),
        feature_read_max_kb=env.whole("FEATURE_READ_MAX_KB", 200),
        feature_max_claims=env.whole("FEATURE_MAX_CLAIMS", 12),
    )
    copy = CopySettings(
        review_pct=env.decimal("COPY_REVIEW_PCT", 40.0, 1.0, 100.0),
        strong_pct=env.decimal("COPY_STRONG_PCT", 70.0, 1.0, 100.0),
        starter_share=env.decimal("COPY_STARTER_SHARE", 0.5, 0.1, 1.0),
        max_teams=env.whole("COPY_MAX_TEAMS", 60),
        look_max_files=env.whole("COPY_LOOK_MAX_FILES", 3),
    )
    authorship = AuthorshipSettings(
        locate_max_files=env.whole("AUTHORSHIP_LOCATE_MAX_FILES", 40),
        max_claims=env.whole("AUTHORSHIP_MAX_CLAIMS", 25),
        max_files_per_claim=env.whole("AUTHORSHIP_MAX_FILES_PER_CLAIM", 6),
        min_confidence=env.decimal("AUTHORSHIP_MIN_CONFIDENCE", 0.6, 0.0, 1.0),
        top_commits=env.whole("AUTHORSHIP_TOP_COMMITS", 8),
        one_drop_share=env.decimal("AUTHORSHIP_ONE_DROP_SHARE", 0.8, 0.0, 1.0),
        before_event_review=env.decimal("AUTHORSHIP_BEFORE_EVENT_REVIEW", 0.3, 0.0, 1.0),
        before_event_strong=env.decimal("AUTHORSHIP_BEFORE_EVENT_STRONG", 0.6, 0.0, 1.0),
        claimed_min_share=env.decimal("AUTHORSHIP_CLAIMED_MIN_SHARE", 0.2, 0.0, 1.0),
        reformat_share=env.decimal("AUTHORSHIP_REFORMAT_SHARE", 0.5, 0.0, 1.0),
    )
    walkthrough = WalkthroughSettings(
        max_files=env.whole("WALKTHROUGH_MAX_FILES", 8),
        max_lines_per_file=env.whole("WALKTHROUGH_MAX_LINES_PER_FILE", 120),
        snippet_lines=env.whole("WALKTHROUGH_SNIPPET_LINES", 20),
        whisper_model=env.optional("WHISPER_MODEL", "small"),
        whisper_device=env.one_of("WHISPER_DEVICE", "cpu", ("cpu", "cuda")),
        whisper_compute_type=env.optional("WHISPER_COMPUTE_TYPE", "int8"),
    )
    leetcode_replay = LeetCodeReplaySettings(
        contests=env.whole("LEETCODE_REPLAY_CONTESTS", 5),
        rating_jump=env.whole("LEETCODE_REPLAY_RATING_JUMP", 100),
        settle_days=env.whole("LEETCODE_REPLAY_SETTLE_DAYS", 7),
        paste_min_lines=env.whole("LEETCODE_PASTE_MIN_LINES", 4),
        template_seconds=env.whole("LEETCODE_PASTE_TEMPLATE_SECONDS", 60),
        max_edits_after=env.whole("LEETCODE_PASTE_MAX_EDITS_AFTER", 3),
        repeat_contests=env.whole("LEETCODE_PASTE_REPEAT_CONTESTS", 3),
        match_min_lines=env.whole("LEETCODE_MATCH_MIN_LINES", 12),
        match_pages=env.whole("LEETCODE_MATCH_PAGES", 5),
        match_pct=env.decimal("LEETCODE_MATCH_PCT", 90.0, 50.0, 100.0),
        match_min_users=env.whole("LEETCODE_MATCH_MIN_USERS", 2),
    )
    tour = TourSettings(
        max_browser_steps=env.whole("TOUR_MAX_BROWSER_STEPS", 12),
        vm_minutes=env.whole("TOUR_VM_MINUTES", 30),
        guide_max_tool_calls=env.whole("TOUR_GUIDE_MAX_TOOL_CALLS", 12),
        repo_max_mb=env.whole("TOUR_REPO_MAX_MB", 30),
        file_max_kb=env.whole("TOUR_FILE_MAX_KB", 200),
        max_files=env.whole("TOUR_MAX_FILES", 3000),
    )
    database_url = env.required("DATABASE_URL")

    env.stop_if_bad()
    return Settings(database_url=database_url, s3=s3, worker=worker, llm=llm, limits=limits, tinyfish=tinyfish,
                    runner=runner, email=email, phone=phone, sandbox=sandbox, copy=copy, authorship=authorship,
                    walkthrough=walkthrough, tour=tour, leetcode_replay=leetcode_replay,
                    report_coding_wait_seconds=env.whole("REPORT_CODING_WAIT_SECONDS", 480), leetcode_graphql_url=env.url("LEETCODE_GRAPHQL_URL", required=False),
                    browserless_cdp_url=env.url("BROWSERLESS_CDP_URL", required=False),
                    browserless_token=env.optional("BROWSERLESS_TOKEN"),
                    browserless_bql_url=env.url("BROWSERLESS_BQL_URL", required=False),
                    linkedin_email=env.optional("LINKEDIN_EMAIL"), linkedin_password=env.optional("LINKEDIN_PASSWORD"))
