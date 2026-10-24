"""The Tour plan: what the guide says at each step of a guided tour, the proof for it, and what to show in the browser
(architecture section 32). Defined here so the guide, the check and the page all read the same shape."""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _cut(limit: int):
    # A model may run long; trim instead of failing a whole tour over one sentence.
    return BeforeValidator(lambda v: v.strip()[:limit] if isinstance(v, str) else v)


class _Shape(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class TourProof(_Shape):
    """Where a spoken sentence comes from. `code` points at lines of a file; the other kinds point at results TalNex
    already stored."""

    kind: Literal["code", "screenshot", "step", "note"]
    file: Optional[str] = None
    start: Optional[int] = Field(default=None, ge=1)
    end: Optional[int] = Field(default=None, ge=1)
    commit: Optional[str] = None
    key: Optional[str] = None
    text: Annotated[Optional[str], _cut(400)] = None


class TourStep(_Shape):
    say: Annotated[str, _cut(600)] = Field(min_length=3)
    proof: list[TourProof] = Field(default_factory=list, max_length=6)
    # What to do in the browser to show it, in plain words ("add a todo called TalNex test milk and press Enter").
    show: Annotated[Optional[str], _cut(300)] = None
    # What should be visible afterwards.
    expect: Annotated[Optional[str], _cut(300)] = None


class TourPlan(_Shape):
    """Steps in the order a request moves through the code. No steps and a `not_found` reason means "I couldn't find
    that in the code"."""

    steps: list[TourStep] = Field(default_factory=list, max_length=10)
    not_found: Annotated[Optional[str], _cut(400)] = None
