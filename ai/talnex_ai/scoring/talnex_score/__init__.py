"""Feature scores out of 10 and the TalNex score (architecture sections 14 and 29)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from talnex_ai.formats import RoleLevel
from talnex_ai.llm.structured import ChatClient
from talnex_ai.scoring.talnex_score.checklist import (
    Checklist, mark_checklist, mechanism_missing, parts_from_marks, reason_line, write_checklist,
)
from talnex_ai.scoring.talnex_score.feature import (
    PARTS, FeatureItem, FeatureScore, PartScores, TalnexScore, score_feature, talnex_score,
)
from talnex_ai.scoring.talnex_score.groups import (
    ClaimOutcome, CriterionGroup, GroupScore, WeightedTotal, group_score, weighted_total,
)


@dataclass(frozen=True)
class FeatureGrade:
    """What's saved for one feature: its score, the one-line reason, and the evidence behind them."""

    score: Optional[float]
    reason: str
    breakdown: dict[str, Any] = field(default_factory=dict)


def grade_feature(
    client: ChatClient,
    claim_text: str,
    group: str,
    role: RoleLevel,
    verdict: str,
    evidence: str,
    *,
    checklist: Optional[Checklist] = None,
    job_id: Optional[str] = None,
) -> FeatureGrade:
    """Score one tested feature.

    Pass the `checklist` written before the tests ran. If it's not given, it's written now from the
    claim alone (it never sees the evidence). A feature that couldn't be tested, or is broken, needs
    no model at all."""
    if verdict == "could_not_test":
        return FeatureGrade(None, "not scored: it could not be tested", {"role": role, "verdict": verdict})
    if verdict == "broken":
        fs = score_feature(verdict, PartScores(), role)
        return FeatureGrade(fs.score, f"0/10 for {role}: {fs.zero_reason}", {"role": role, "verdict": verdict})

    checklist = checklist or write_checklist(client, claim_text, group, role, job_id=job_id,
                                             from_code=verdict == "reviewed_from_code")
    marks = mark_checklist(client, checklist, claim_text, evidence, job_id=job_id)
    parts = parts_from_marks(checklist, marks)
    # "Claimed but not implemented" comes from reading code. A feature the live test SAW working is
    # implemented by definition: what happened on screen decides, so the marker's doubt can't zero it.
    missing = mechanism_missing(checklist, marks) and verdict not in ("works", "partly_works")
    fs: FeatureScore = score_feature(verdict, parts, role, mechanism_missing=missing)

    capped_note = None
    if fs.capped and fs.cap is not None:
        capped_note = f"capped at {fs.cap:g}: it only partly works" if verdict == "partly_works" else f"capped at {fs.cap:g}"
    line = reason_line(fs.score, role, checklist, marks, zero_reason=fs.zero_reason, capped_note=capped_note,
                       reviewed_only=verdict == "reviewed_from_code")
    breakdown = {
        "role": role,
        "verdict": verdict,
        "checklist": [i.model_dump() for i in checklist.items],
        "marks": [m.model_dump() for m in marks.marks],
        "mechanism_present": marks.mechanism_present,
        "parts": {p: parts.get(p) for p in PARTS},
        "weights_used": dict(fs.weights_used),
        "unmeasured": list(fs.unmeasured),
        "cap": fs.cap,
        "zero_reason": fs.zero_reason,
    }
    return FeatureGrade(fs.score, line, breakdown)


__all__ = [
    "Checklist", "ClaimOutcome", "CriterionGroup", "FeatureGrade", "FeatureItem", "FeatureScore", "GroupScore",
    "PartScores", "TalnexScore", "WeightedTotal", "grade_feature", "group_score", "score_feature", "talnex_score",
    "weighted_total",
]
