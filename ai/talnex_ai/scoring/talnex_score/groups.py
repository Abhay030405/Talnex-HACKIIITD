"""Group scores (architecture section 14). Pure functions.

  group score = sum(importance x points) / sum(importance), over the tested claims, x 100
  coverage    = tested claims / all testable claims in the group
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from talnex_ai.scoring.claim_points import confidence_value, points

LOW_COVERAGE_PERCENT = 50.0


@dataclass(frozen=True)
class ClaimOutcome:
    importance: int
    verdict: str
    confidence: str = "medium"
    testable: bool = True
    # 0 to 1. A claim reviewed from code has no points of its own, so it counts by its feature score
    # out of 10 (already capped at 7), so a project judged only by its code still gets a group score.
    points_override: Optional[float] = None


@dataclass(frozen=True)
class GroupScore:
    score: Optional[float]     # 0 to 100, None when nothing was tested
    coverage: float            # percent
    confidence: Optional[str]  # high / medium / low, None when nothing was tested
    claims_used: int
    low_coverage: bool         # shown greyed, and left out of feature comparison


def _points(c: ClaimOutcome) -> Optional[float]:
    if c.verdict == "reviewed_from_code" and c.points_override is not None:
        return c.points_override
    return points(c.verdict)


def group_confidence(values: list[float]) -> Optional[str]:
    """Average claim confidence: above 0.75 high, 0.45 to 0.75 medium, below that low."""
    if not values:
        return None
    mean = sum(values) / len(values)
    return "high" if mean > 0.75 else "medium" if mean >= 0.45 else "low"


def group_score(claims: Iterable[ClaimOutcome]) -> GroupScore:
    testable = [c for c in claims if c.testable]
    tested = [c for c in testable if _points(c) is not None and confidence_value(c.confidence) is not None]
    coverage = round(100.0 * len(tested) / len(testable), 1) if testable else 0.0
    if not tested:
        return GroupScore(None, coverage, None, 0, low_coverage=True)
    weight = sum(c.importance for c in tested)
    total = sum(c.importance * _points(c) for c in tested)
    return GroupScore(
        score=round(100.0 * total / weight, 1),
        coverage=coverage,
        confidence=group_confidence([confidence_value(c.confidence) for c in tested]),
        claims_used=len(tested),
        low_coverage=coverage < LOW_COVERAGE_PERCENT,
    )


@dataclass(frozen=True)
class CriterionGroup:
    """One organizer criterion: how much it counts, and how its claims scored."""

    weight: float
    group: GroupScore


@dataclass(frozen=True)
class WeightedTotal:
    score: Optional[float]   # 0 to 100, None when no criterion could be scored
    weight_covered: float    # percent of the organizer's total weight that was scored
    criteria_used: int
    criteria_total: int


def weighted_total(criteria: Iterable[CriterionGroup]) -> WeightedTotal:
    """Fixed-problem events: sum(weight x group score) / sum(weight), over the criteria that were scored.

    A criterion with nothing tested is left out and the rest are rescaled, the same way "could not
    test" is left out everywhere; `weight_covered` says how much of the organizer's weight the number
    rests on. It's shown as "based on your criteria and tested claims only", never as a ranking."""
    items = list(criteria)
    scored = [c for c in items if c.group.score is not None]
    total_weight = sum(c.weight for c in items)
    if not scored or total_weight <= 0:
        return WeightedTotal(None, 0.0, 0, len(items))
    used_weight = sum(c.weight for c in scored)
    return WeightedTotal(
        score=round(sum(c.weight * c.group.score for c in scored) / used_weight, 1),
        weight_covered=round(100.0 * used_weight / total_weight, 1),
        criteria_used=len(scored),
        criteria_total=len(items),
    )
