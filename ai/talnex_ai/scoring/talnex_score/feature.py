"""Feature scores out of 10, and the TalNex score (architecture section 29). Pure functions.

A feature scores 0 when it was tested and is broken, or when the claimed mechanism isn't really
implemented. Otherwise the score is how well it's implemented, judged for the role level, then
capped by how much we actually saw (partly works: 5, reviewed from code: 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Mapping, Optional

from talnex_ai.formats import RoleLevel
from talnex_ai.scoring.claim_points import confidence_value
from talnex_ai.scoring.talnex_score.groups import LOW_COVERAGE_PERCENT, group_confidence

PARTS = ("implementation", "logic", "edge", "design")

# Percent of the 10 points each part is worth. A fresher is judged on how it's implemented, not on
# design (weight 0). Starting values, to be tuned on real data.
ROLE_WEIGHTS: Mapping[str, Mapping[str, int]] = {
    "fresher": {"implementation": 50, "logic": 35, "edge": 15, "design": 0},
    "junior": {"implementation": 40, "logic": 30, "edge": 20, "design": 10},
    "mid": {"implementation": 35, "logic": 25, "edge": 25, "design": 15},
    "senior": {"implementation": 30, "logic": 25, "edge": 25, "design": 20},
}

CAPS: Mapping[str, float] = {"works": 10.0, "partly_works": 5.0, "reviewed_from_code": 7.0}


@dataclass(frozen=True)
class PartScores:
    """Each part from 0 to 1, or None when there's no evidence for it."""

    implementation: Optional[float] = None
    logic: Optional[float] = None
    edge: Optional[float] = None
    design: Optional[float] = None

    def get(self, part: str) -> Optional[float]:
        return getattr(self, part)


@dataclass(frozen=True)
class FeatureScore:
    score: Optional[float]               # 0 to 10, None when it can't be scored
    zero_reason: Optional[str] = None    # set when the score is a zero case
    cap: Optional[float] = None
    capped: bool = False
    weights_used: Mapping[str, float] = field(default_factory=dict)  # after scaling up for missing evidence
    unmeasured: tuple[str, ...] = ()     # parts that count for this role but had no evidence


def round1(value: float) -> float:
    """Round to one decimal the way people expect (2.25 -> 2.3), not banker's rounding (2.25 -> 2.2)."""
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def score_feature(verdict: str, parts: PartScores, role: RoleLevel, *, mechanism_missing: bool = False) -> FeatureScore:
    if verdict == "could_not_test":
        return FeatureScore(None)
    if verdict == "broken":
        return FeatureScore(0.0, zero_reason="tested and not working")
    if mechanism_missing:
        return FeatureScore(0.0, zero_reason="claimed, but the mechanism is not implemented")
    if verdict not in CAPS:
        raise ValueError(f"cannot score a feature with verdict {verdict!r}")

    counted = {p: w for p, w in ROLE_WEIGHTS[role].items() if w > 0}
    measured = {p: w for p, w in counted.items() if parts.get(p) is not None}
    unmeasured = tuple(p for p in counted if p not in measured)
    if not measured:
        return FeatureScore(None, unmeasured=unmeasured)

    # A part with no evidence is left out, and the other weights are scaled up to fill its place.
    total_weight = sum(measured.values())
    raw = 10.0 * sum(w * parts.get(p) for p, w in measured.items()) / total_weight
    cap = CAPS[verdict]
    return FeatureScore(
        score=round1(min(raw, cap)),
        cap=cap,
        capped=raw > cap,
        weights_used={p: round(100.0 * w / total_weight, 1) for p, w in measured.items()},
        unmeasured=unmeasured,
    )


@dataclass(frozen=True)
class FeatureItem:
    importance: int
    score: Optional[float]       # None = couldn't be scored (left out)
    testable: bool = True
    confidence: str = "medium"   # of the claim behind this feature


@dataclass(frozen=True)
class TalnexScore:
    score10: Optional[float]     # shown out of 10
    stored: Optional[float]      # 0 to 100, as kept in the scores table
    coverage: float              # percent of testable features that were scored
    features_used: int
    low_coverage: bool           # below 50 percent: shown greyed
    confidence: Optional[str] = None


def talnex_score(items: Iterable[FeatureItem]) -> TalnexScore:
    """sum(importance x score) / sum(importance), over the scored features. Never a ranking; flags never subtract."""
    testable = [i for i in items if i.testable]
    scored = [i for i in testable if i.score is not None]
    coverage = round(100.0 * len(scored) / len(testable), 1) if testable else 0.0
    if not scored:
        return TalnexScore(None, None, coverage, 0, low_coverage=True)
    score10 = round1(sum(i.importance * i.score for i in scored) / sum(i.importance for i in scored))
    return TalnexScore(
        score10=score10,
        stored=round1(score10 * 10),
        coverage=coverage,
        features_used=len(scored),
        low_coverage=coverage < LOW_COVERAGE_PERCENT,
        confidence=group_confidence([v for v in (confidence_value(i.confidence) for i in scored) if v is not None]),
    )
