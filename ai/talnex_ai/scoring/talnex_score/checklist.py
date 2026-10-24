"""Checklist scoring: a model writes a checklist BEFORE seeing any results, then marks it against
the evidence. Everything after the marks (part scores, the zero rule, the reason line) is plain code.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from talnex_ai.formats import FormatError, RoleLevel, parse_model
from talnex_ai.llm.prompts.feature_score import CHECKLIST_SYSTEM, MARK_SYSTEM, checklist_user, mark_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.scoring.talnex_score.feature import PARTS, PartScores

Part = Literal["implementation", "logic", "edge", "design"]
Status = Literal["present", "missing", "unknown"]
MAX_REASON = 260


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChecklistItem(_Shape):
    text: str = Field(min_length=3, max_length=60)
    part: Part
    core: bool = False


class Checklist(_Shape):
    items: list[ChecklistItem] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def _needs_a_core_implementation_item(self) -> "Checklist":
        if not any(i.core and i.part == "implementation" for i in self.items):
            raise ValueError("at least one core item about the real implementation is required")
        return self


class ItemMark(_Shape):
    index: int = Field(ge=1)
    status: Status
    note: str = Field(default="", max_length=140)


class Marks(_Shape):
    marks: list[ItemMark]
    mechanism_present: Optional[bool] = None


def write_checklist(client: ChatClient, claim_text: str, group: str, role: RoleLevel, *,
                    job_id: Optional[str] = None, from_code: bool = False, brief: str = "") -> Checklist:
    """The checklist for a feature, written from the claim alone, before any results are seen.

    By default the feature will be tested on its live site, so every item is something a visitor
    can see or try. `from_code=True` is for judging a project's code, where items may describe it."""
    return ask_json(client, "claim_reader", CHECKLIST_SYSTEM,
                    checklist_user(claim_text, group, role, from_code=from_code, brief=brief),
                    lambda text: parse_model(Checklist, text), job_id=job_id)


def mark_checklist(client: ChatClient, checklist: Checklist, claim_text: str, evidence: str, *,
                   job_id: Optional[str] = None) -> Marks:
    """Mark every checklist item present, missing or unknown from the evidence."""
    items = [(n, item.part, item.text) for n, item in enumerate(checklist.items, start=1)]

    def parse(text: str) -> Marks:
        marks = parse_model(Marks, text)
        ordered = sorted(marks.marks, key=lambda m: m.index)  # models sometimes answer out of order
        if [m.index for m in ordered] != list(range(1, len(checklist.items) + 1)):
            raise FormatError(f"give exactly one mark per item, numbered 1 to {len(checklist.items)}")
        return marks.model_copy(update={"marks": ordered})

    return ask_json(client, "proof_checker", MARK_SYSTEM, mark_user(items, claim_text, evidence), parse, job_id=job_id)


# ---- everything below is plain code ----


def parts_from_marks(checklist: Checklist, marks: Marks) -> PartScores:
    """Each part is the share of its known items that are present. A part with no known item is None."""
    values: dict[str, Optional[float]] = {}
    for part in PARTS:
        known = [m.status for item, m in zip(checklist.items, marks.marks) if item.part == part and m.status != "unknown"]
        values[part] = known.count("present") / len(known) if known else None
    return PartScores(**values)


def mechanism_missing(checklist: Checklist, marks: Marks) -> bool:
    """True when the claimed mechanism is shown to be absent: the marker says so, or every core item is missing."""
    if marks.mechanism_present is False:
        return True
    core = [m.status for item, m in zip(checklist.items, marks.marks) if item.core]
    return bool(core) and all(s == "missing" for s in core)


def reason_line(score: Optional[float], role: str, checklist: Checklist, marks: Marks, *,
                zero_reason: Optional[str] = None, capped_note: Optional[str] = None,
                reviewed_only: bool = False) -> str:
    """One line saying what raised and what lowered the score, built from the marks."""
    if score is None:
        return "not scored: there was not enough evidence"
    if zero_reason:
        body = zero_reason
    else:
        def texts(status: str) -> list[str]:
            return [item.text for item, m in zip(checklist.items, marks.marks) if m.status == status][:2]

        bits = []
        if texts("present"):
            bits.append("+ " + "; ".join(texts("present")))
        if texts("missing"):
            bits.append("- " + "; ".join(texts("missing")))
        if texts("unknown"):
            bits.append("? not checked: " + "; ".join(texts("unknown")))
        body = " ".join(bits) or "no clear strengths or gaps were seen"
    notes = [n for n in (capped_note, "reviewed from code, not run" if reviewed_only else None) if n]
    line = f"{score:g}/10 for {role}: {body}" + (f" ({'; '.join(notes)})" if notes else "")
    return line if len(line) <= MAX_REASON else line[:MAX_REASON - 3] + "..."
