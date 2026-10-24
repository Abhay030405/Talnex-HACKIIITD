"""From evidence to a verdict, a confidence level and points (architecture section 13). Pure functions.

The never-blame rule lives here: a claim is only ever Broken when the never-blame ladder was cleared
AND an independent second check agrees it failed. Anything else that goes wrong is "could not test",
which is left out of scores and never counts against the team.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

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
    # Per-check marks from the run and from the independent check (same order), when the plan had checks.
    agent_parts: tuple[str, ...] = ()
    checker_parts: tuple[str, ...] = ()
    part_names: tuple[str, ...] = ()


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


def outcome_from_parts(marks: Sequence[str]) -> Outcome:
    """One judge's outcome from its marks: every part seen works; a part not seen makes it partly working, or
    broken when nothing was seen; a part that couldn't be judged means the test could not show it (blocked)."""
    parts = [m for m in marks if m != "beyond_claim"]
    if not parts:
        return "blocked"
    if all(m == "seen" for m in parts):
        return "works"
    if "not_seen" in parts:
        return "partly_works" if "seen" in parts else "broken"
    return "blocked"


def merge_part(run: str, check: str) -> tuple[str, int]:
    """One part, from both judges: (status, how many judges back it). A part is only "not seen" when BOTH say so:
    one judge alone never blames. When they contradict each other the part is "disputed"."""
    marks = {run, check} - {"beyond_claim"}
    if not marks:
        return "beyond_claim", 2
    if run == "beyond_claim" or check == "beyond_claim":
        # One judge says the part is beyond the claim. The other judge alone can confirm it was seen, but can never
        # blame on its own, so anything less than "seen" leaves the part out.
        only = run if check == "beyond_claim" else check
        return ("seen", 1) if only == "seen" else ("beyond_claim", 1)
    if run == check:
        return run, 2 if run != "cant_tell" else 0
    if marks == {"seen", "not_seen"}:
        return "disputed", 2
    known = run if check == "cant_tell" else check
    return ("cant_tell", 0) if known == "not_seen" else (known, 1)


def _name(e: Evidence, i: int) -> str:
    return e.part_names[i] if i < len(e.part_names) else f"part {i + 1}"


def _decide_parts(e: Evidence) -> Decision:
    merged = [merge_part(a, c) for a, c in zip(e.agent_parts, e.checker_parts)]
    judged = [(i, s, n) for i, (s, n) in enumerate(merged) if s != "beyond_claim"]
    if not judged:
        return Decision("could_not_test", "low", "no part of the claim could be judged")
    disputed = [_name(e, i) for i, s, _ in judged if s == "disputed"]
    seen = [_name(e, i) for i, s, _ in judged if s == "seen"]
    missing = [_name(e, i) for i, s, _ in judged if s == "not_seen"]
    unknown = [_name(e, i) for i, s, _ in judged if s == "cant_tell"]
    if disputed:
        return Decision("could_not_test", "disagree", "the run and the independent check disagree on: " + "; ".join(disputed))
    if len(seen) == len(judged):
        if any(n < 2 for _, _, n in judged):
            return Decision("works", "low", f"all {len(seen)} parts were seen, some by only one of the two checks")
        confidence, reason = _agreed_confidence(e)
        return Decision("works", confidence, f"all {len(seen)} parts were seen; {reason}")
    if missing and seen:
        return Decision("partly_works", "medium" if not unknown else "low",
                        f"{len(seen)} of {len(judged)} parts work; not working: " + "; ".join(missing))
    if missing and not seen:
        if not e.ladder_cleared:
            return Decision("could_not_test", "low", "it looked broken, but the never-blame steps were not completed")
        return Decision("broken", "medium" if not unknown else "low", "not working: " + "; ".join(missing))
    return Decision("could_not_test", "low", "these parts could not be shown by the test: " + "; ".join(unknown))


def decide(e: Evidence) -> Decision:
    """The verdict and confidence for one claim."""
    if e.agent_parts and e.checker_parts and len(e.agent_parts) == len(e.checker_parts):
        return _decide_parts(e)
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
