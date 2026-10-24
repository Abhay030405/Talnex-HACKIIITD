"""The parts of a claim, judged one by one.

A main test plan breaks its claim into a few small checks, each tied to the claim's own words (a quote).
Both judges, the run's own final look and the independent screenshot check, mark every check:

  seen          the page clearly shows it
  not_seen      the test did the step and the page clearly shows it is NOT so (an error page caused by the
                action counts here: that is what the feature did)
  cant_tell     the step was not carried out, or the result can't be made out: the test's problem, never the site's
  beyond_claim  the check asks for more than the claim says, so it is left out

Plain code then turns the marks into a verdict (scoring/claim_points), so a long free-text answer can't drift.
"""
from __future__ import annotations

from typing import Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import FormatError

Status = Literal["seen", "not_seen", "cant_tell", "beyond_claim"]


class PartMark(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    n: int = Field(ge=1)
    status: Status
    note: str = Field(default="", max_length=300)
    shot: Optional[int] = None  # which screenshot shows it (the independent check only)


def numbered(checks: Sequence) -> str:
    """The checks as the judges see them: number, what must be visible, and the claim words it proves."""
    return "\n".join(f'{i}. {c.text}  (proves the claim words: "{c.quote}")' if c.quote else f"{i}. {c.text}"
                     for i, c in enumerate(checks, start=1))


def read_marks(marks: Sequence[PartMark], count: int) -> tuple[Status, ...]:
    """One status per check, in order. Raises FormatError (one repair try) unless every check is marked once."""
    by_number = {}
    for m in marks:
        if m.n > count:
            raise FormatError(f"there are only {count} checks, but a mark was given for check {m.n}")
        if m.n in by_number:
            raise FormatError(f"check {m.n} was marked twice; mark each check exactly once")
        by_number[m.n] = m.status
    missing = [n for n in range(1, count + 1) if n not in by_number]
    if missing:
        raise FormatError(f"no mark was given for check(s) {', '.join(map(str, missing))}; mark every check")
    return tuple(by_number[n] for n in range(1, count + 1))


SCALE = """Mark EVERY check with one status:
- "seen": the page clearly shows it.
- "not_seen": the test carried out the steps for it and the page clearly shows it is NOT so. An error message, error page or blank page that appeared because of an action is "not_seen": that is what the feature did.
- "cant_tell": the steps for it were not carried out (skipped, failed on our side, ran out of time), or the result can't be made out. This is the test's problem, never the site's.
- "beyond_claim": the check asks for more than the claim's words promise. It is left out; never let it count against the claim.
Judge each check on its own. One check failing says nothing about the others."""
