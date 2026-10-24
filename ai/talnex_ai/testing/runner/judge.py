"""The run's own final look: after the steps, did the page show what the claim promises?

This is the judging layer. The step loop that drives the browser (executor.py) hands over what was done and the
final page, and gets back an outcome. With checks, the look marks each check and plain code decides the outcome
(scoring/claim_points); without checks (older plans) it gives one verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import FormatError, TestPlan, parse_model
from talnex_ai.llm.prompts.runner import FINAL_PARTS_SYSTEM, FINAL_SYSTEM, final_parts_user, final_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.scoring.claim_points import outcome_from_parts
from talnex_ai.testing.checks import PartMark, numbered, read_marks
from talnex_ai.testing.runner.actions import FinalVerdict
from talnex_ai.testing.scope import unchanged_value

INCOMPLETE = "the test could not show every part of the claim"


@dataclass(frozen=True)
class FinalLook:
    outcome: str                      # works / partly_works / broken / blocked
    observed: str
    stop_reason: Optional[str] = None
    parts: tuple[str, ...] = ()       # one mark per plan check, when the plan had checks


class _FinalParts(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    checks: list[PartMark] = Field(min_length=1)
    observed: str = Field(min_length=1, max_length=600)


def _final_parts(text: str, claim_text: str, count: int) -> tuple[tuple[str, ...], str]:
    """The run's marks for each check, and what it saw. A count or progress "seen" at its starting value is sent back."""
    answer = parse_model(_FinalParts, text)
    marks = read_marks(answer.checks, count)
    for m in answer.checks:
        start = unchanged_value(claim_text, m.note) if m.status == "seen" else None
        if start:
            raise FormatError(f'check {m.n} is marked seen, but its note describes a starting value ("{start}"), which would '
                              "look the same if the feature did nothing. Mark it not_seen, or say how the value changed.")
    return marks, answer.observed


def _final(text: str, claim_text: str) -> FinalVerdict:
    """The run's own verdict (plans without checks). "works" resting on a starting value is sent back."""
    verdict = parse_model(FinalVerdict, text)
    start = unchanged_value(claim_text, verdict.observed) if verdict.verdict == "works" else None
    if start:
        raise FormatError(f'the verdict is works, but the value you describe ("{start}") is still at its starting point, '
                          "which would look the same if the feature did nothing. Answer partly_works or broken, unless "
                          'the test changed the value on purpose: then say how it changed ("went from 1 to 0").')
    return verdict


def final_look(client: ChatClient, plan: TestPlan, *, claim_text: str, history: Sequence[str], url: str, snapshot: str,
               job_id: Optional[str] = None) -> FinalLook:
    """Judge the finished run against the plan: per check when it has checks, as a whole otherwise."""
    if plan.checks:
        marks, observed = ask_json(
            client, "agent", FINAL_PARTS_SYSTEM,
            final_parts_user(claim=claim_text, checks=numbered(plan.checks), history=history, url=url, snapshot=snapshot),
            lambda text: _final_parts(text, claim_text, len(plan.checks)), job_id=job_id,
        )
        outcome = outcome_from_parts(marks, [c.promise for c in plan.checks])
        return FinalLook(outcome, observed, INCOMPLETE if outcome == "blocked" else None, marks)
    verdict = ask_json(
        client, "agent", FINAL_SYSTEM,
        final_user(claim=claim_text, expected_result=plan.expected_result, history=history, url=url, snapshot=snapshot),
        lambda text: _final(text, claim_text), job_id=job_id,
    )
    return FinalLook(verdict.verdict, verdict.observed, "blocked" if verdict.verdict == "blocked" else None)
