"""From evidence to a verdict, a confidence level and points (architecture section 13). Pure functions.

The never-blame rule lives here: a claim is only ever Broken when the never-blame ladder was cleared
AND an independent second check agrees it failed. Anything else that goes wrong is "could not test",
which is left out of scores and never counts against the team.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from talnex_ai.formats import Confidence, Verdict

Outcome = Literal["works", "partly_works", "broken", "blocked"]

POINTS: dict[str, float] = {"works": 1.0, "partly_works": 0.5, "broken": 0.0}
CONFIDENCE_VALUE: dict[str, float] = {"high": 1.0, "medium": 0.6, "low": 0.3}


@dataclass(frozen=True)
class Evidence:
    agent: Outcome                        # what the test run concluded
    checker: Optional[Outcome] = None     # the independent second check; None if it wasn't done
    tries: int = 1                        # complete tries made
    repeat_agrees: Optional[bool] = None  # did a repeat try give the same outcome? None if not repeated
    screenshot_clear: bool = True
    backup_method_used: bool = False
    ladder_cleared: bool = False          # the never-blame ladder passed (needed before "broken")


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    confidence: Confidence
    reason: str


def points(verdict: str) -> Optional[float]:
    """1.0 works, 0.5 partly works, 0 broken. Anything else is left out of scores (None)."""
    return POINTS.get(verdict)


def confidence_value(confidence: str) -> Optional[float]:
    """High 1, medium 0.6, low 0.3. "disagree" has no value: that claim isn't scored."""
    return CONFIDENCE_VALUE.get(confidence)


def decide(e: Evidence) -> Decision:
    """The verdict and confidence for one claim."""
    if "blocked" in (e.agent, e.checker):
        return Decision("could_not_test", "low", "could not reach or try the feature (blocked)")

    if e.checker is None:
        if e.agent == "broken":
            return Decision("could_not_test", "low", "it looked broken, but no independent check confirmed it")
        return Decision(e.agent, "low", "one source only: the independent check was not done")

    if e.agent == e.checker:
        if e.agent == "broken" and not e.ladder_cleared:
            return Decision("could_not_test", "low", "both looked broken, but the never-blame steps were not completed")
        confidence, reason = _agreed_confidence(e)
        return Decision(e.agent, confidence, reason)

    # The two disagree.
    if {e.agent, e.checker} == {"works", "partly_works"}:
        return Decision("partly_works", "low", "the checks differ slightly, so the cautious reading is used")
    return Decision("could_not_test", "disagree", "the test run and the independent check disagree, so it is not confirmed")


def _agreed_confidence(e: Evidence) -> tuple[Confidence, str]:
    if e.backup_method_used:
        return "low", "agreed, but a backup way of testing was used"
    if e.repeat_agrees is False:
        return "low", "agreed, but a repeat try gave a different result"
    if e.repeat_agrees and e.screenshot_clear and e.tries >= 2:
        return "high", "the run and the independent check agree, and a repeat try matches"
    if not e.screenshot_clear:
        return "medium", "they agree, but the screenshot is a little unclear"
    return "medium", "they agree, from a single try"
