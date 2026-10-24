"""The typed shapes. Allowed values must match the CHECK constraints in backend/migrations,
or the database will refuse what we try to save."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Verdict = Literal["works", "partly_works", "broken", "could_not_test", "reviewed_from_code"]
Confidence = Literal["high", "medium", "low", "disagree"]
RoleLevel = Literal["fresher", "junior", "mid", "senior"]
ClaimSource = Literal["video", "criteria", "resume", "readme", "route", "code"]
Track = Literal["live", "sandbox", "both"]
StepKind = Literal["screen", "http", "command"]
TestType = Literal[
    "normal", "demo_replay", "known_answer", "repeat", "bad_input", "access",
    "setup", "route_smoke", "edge_case", "light_load", "repo_tests",
]


class _Shape(BaseModel):
    # A model answer with fields we never asked for didn't follow the format, so it's refused
    # rather than half-trusted.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Claim(_Shape):
    """One thing a project says it can do."""

    id: Optional[str] = None
    text: str = Field(min_length=3, max_length=400)
    claim_group: str = Field(min_length=1, max_length=60)
    importance: Literal[1, 2, 3] = Field(description="3 = main feature, 2 = supporting, 1 = minor")
    source: ClaimSource
    track: Track = "live"
    testable: bool = True
    untestable_reason: Optional[str] = None

    @model_validator(mode="after")
    def _untestable_needs_a_reason(self) -> "Claim":
        if not self.testable and not (self.untestable_reason or "").strip():
            raise ValueError("an untestable claim must say why (untestable_reason)")
        return self


class PlanStep(_Shape):
    action: str = Field(min_length=3, description="What to do, in plain words")
    expected: str = Field(min_length=3, description="What should be on screen afterwards")


class TestPlan(_Shape):
    """The steps to check one claim in one way, and what should happen at the end."""

    __test__ = False  # the name starts with "Test", but pytest must not collect it

    claim_id: Optional[str] = None
    test_type: TestType
    steps: list[PlanStep] = Field(min_length=1, max_length=12)
    expected_result: str = Field(min_length=3)


class StepRecord(_Shape):
    """What actually happened in one step, and where its proof is stored."""

    step_number: int = Field(ge=1)
    kind: StepKind = "screen"
    action: str
    expected: Optional[str] = None
    observed: Optional[str] = None
    proof_key: Optional[str] = None  # storage key of the screenshot, the request/response, or the command output
    duration_ms: Optional[int] = Field(default=None, ge=0)
    # What the browser's developer tools saw during the step (runner/devtools.py); None when nothing was watched.
    devtools: Optional[dict] = None


class Result(_Shape):
    """The final answer for one claim."""

    claim_id: str
    verdict: Verdict
    confidence: Confidence
    reason: str = Field(min_length=1)
    proof_keys: list[str] = Field(default_factory=list)
    second_check_agreed: Optional[bool] = None

    @field_validator("proof_keys")
    @classmethod
    def _no_blank_keys(cls, keys: list[str]) -> list[str]:
        if any(not k.strip() for k in keys):
            raise ValueError("proof_keys must not contain blank keys")
        return keys
