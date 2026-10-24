"""Saves results and scores. Go owns the schema; this only writes rows (AGENTS.md rule 11)."""
from __future__ import annotations

import json
from typing import Literal, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.formats import Result
from talnex_ai.scoring.talnex_score import FeatureGrade, GroupScore, TalnexScore, WeightedTotal

ScoreSubject = Literal["project", "candidate_project", "candidate"]
_COLUMN = {"project": "project_id", "candidate_project": "candidate_project_id", "candidate": "candidate_id"}
TALNEX_GROUP = "talnex"
WEIGHTED_TOTAL_GROUP = "weighted_total"


def save_result(pool: ConnectionPool, result: Result, grade: Optional[FeatureGrade] = None) -> None:
    """Save the final result for a claim, with its feature score and reason when it has them.
    Saving again replaces the old result, so a stage that runs twice leaves one row."""
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO results (claim_id, verdict, confidence, reason, second_model_agreed, proof_keys,
                                    feature_score, score_reason, score_breakdown)
               VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (claim_id) DO UPDATE SET
                   verdict = EXCLUDED.verdict, confidence = EXCLUDED.confidence, reason = EXCLUDED.reason,
                   second_model_agreed = EXCLUDED.second_model_agreed, proof_keys = EXCLUDED.proof_keys,
                   feature_score = EXCLUDED.feature_score, score_reason = EXCLUDED.score_reason,
                   score_breakdown = EXCLUDED.score_breakdown""",
            (result.claim_id, result.verdict, result.confidence, result.reason, result.second_check_agreed,
             result.proof_keys, grade.score if grade else None, grade.reason if grade else None,
             json.dumps(grade.breakdown if grade else {})),
        )


def _save_score(pool: ConnectionPool, kind: ScoreSubject, subject_id: str, group: str, score: Optional[float],
                coverage: float, confidence: Optional[str], claims_used: int) -> None:
    column = _COLUMN[kind]  # one of three fixed names, never outside input
    with pool.connection() as conn:
        conn.execute(
            f"""INSERT INTO scores ({column}, score_group, score, coverage, confidence, claims_used)
                VALUES (%s::uuid, %s, %s, %s, %s, %s)
                ON CONFLICT ({column}, score_group) WHERE {column} IS NOT NULL DO UPDATE SET
                    score = EXCLUDED.score, coverage = EXCLUDED.coverage, confidence = EXCLUDED.confidence,
                    claims_used = EXCLUDED.claims_used""",
            (subject_id, group, score, coverage, confidence or "low", claims_used),
        )


def save_group_score(pool: ConnectionPool, kind: ScoreSubject, subject_id: str, group: str, g: GroupScore) -> None:
    _save_score(pool, kind, subject_id, group, g.score, g.coverage, g.confidence, g.claims_used)


def save_talnex_score(pool: ConnectionPool, kind: ScoreSubject, subject_id: str, t: TalnexScore) -> None:
    """Kept on a 0 to 100 scale and shown out of 10, as the `talnex` group."""
    _save_score(pool, kind, subject_id, TALNEX_GROUP, t.stored, t.coverage, t.confidence, t.features_used)


def save_weighted_total(pool: ConnectionPool, project_id: str, t: WeightedTotal) -> None:
    """Fixed-problem events only. `coverage` holds the share of the organizer's weight that was scored."""
    _save_score(pool, "project", project_id, WEIGHTED_TOTAL_GROUP, t.score, t.weight_covered, None, t.criteria_used)
