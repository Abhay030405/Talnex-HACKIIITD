"""The shared shapes that pass between stages, workers and the website (architecture section 21).

They're defined once, here. Every model answer is checked against them before anything is
saved, so a malformed answer fails loudly instead of turning into a made-up result.
"""
from talnex_ai.formats.models import (
    Check,
    Claim,
    ClaimSource,
    Confidence,
    PlanStep,
    Result,
    RoleLevel,
    StepKind,
    StepRecord,
    TestPlan,
    TestType,
    Track,
    Verdict,
)
from talnex_ai.formats.tour import TourPlan, TourProof, TourStep
from talnex_ai.formats.parse import FormatError, parse_json_block, parse_list, parse_model

__all__ = [
    "Check", "Claim", "ClaimSource", "Confidence", "FormatError", "PlanStep", "Result", "RoleLevel",
    "StepKind", "StepRecord", "TestPlan", "TestType", "TourPlan", "TourProof", "TourStep", "Track", "Verdict",
    "parse_json_block", "parse_list", "parse_model",
]
