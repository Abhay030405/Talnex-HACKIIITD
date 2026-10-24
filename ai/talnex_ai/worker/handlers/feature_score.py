"""Stage `feature_score`: a score out of 10, with a one-line reason, for every tested feature, then the TalNex score.

For each claim with a result, the checklist written BEFORE testing (by `test_plan` for live claims, by
`sandbox_plan` for backend claims) is marked against what was actually seen; the owner's role level
sets the weights and plain code does the sums (architecture section 29). A feature that could not be
tested is left out and listed, never counted against anyone.

Works for a hackathon project and a project on a resume alike.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim
from talnex_ai.sandbox.code_review import evidence_text as code_review_text
from talnex_ai.sandbox.store import code_review_for_claim
from talnex_ai.scoring.store import save_talnex_score
from talnex_ai.scoring.talnex_score import FeatureGrade, FeatureItem, grade_feature, talnex_score
from talnex_ai.scoring.talnex_score.checklist import Checklist
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import SubjectInfo, load_subject_info, set_status, stage_result, subject_of

log = logging.getLogger("talnex.feature_score")

GRADING_THREADS = 4
MAX_EVIDENCE_CHARS = 6000
MAIN_TESTS = ("normal", "access")


def _steps(conn, run_id: str) -> list[str]:
    rows = conn.execute("SELECT step_number, action, observed FROM steps WHERE run_id = %s::uuid ORDER BY step_number",
                        (run_id,)).fetchall()
    return [f"{n}. {action}" + (f" -> {seen}" if seen else "") for n, action, seen in rows]


def evidence_text(pool: ConnectionPool, claim_id: str) -> tuple[str, str, str, str]:
    """(verdict, confidence, reason, evidence): what was seen when the claim was tested, as plain text for the marker.

    The main test is the latest normal or access run; a claim TalNex made from the routes (edge cases,
    route checks, the repo's own tests) has none, so its own latest run is the main one. Extra checks
    (bad input, known answer, repeat) are listed separately so the marker can tell which proved what."""
    with pool.connection() as conn:
        verdict, confidence, reason = conn.execute(
            "SELECT verdict, confidence, coalesce(reason, '') FROM results WHERE claim_id = %s::uuid", (claim_id,)).fetchone()
        runs = conn.execute(
            """SELECT id::text, test_type, outcome FROM test_runs WHERE claim_id = %s::uuid
                ORDER BY started_at DESC NULLS LAST, try_number DESC""", (claim_id,)).fetchall()
        main = next((r for r in runs if r[1] in MAIN_TESTS), runs[0] if runs else None)
        lines = [f"Result of the test: {verdict}. {reason}".strip()]
        if main is not None:
            steps = _steps(conn, main[0])
            if steps:
                lines += ["Steps of the main test run:", *steps]
        for run_id, kind, outcome in reversed(runs):
            if main is not None and run_id == main[0] or kind in MAIN_TESTS:
                continue
            steps = _steps(conn, run_id)
            if steps:
                lines += [f"Extra check ({kind.replace('_', ' ')}), run ended: {outcome or 'unknown'}:", *steps]
    review = code_review_for_claim(pool, claim_id)
    if review:
        lines.append(code_review_text(review))
    return verdict, confidence, reason, "\n".join(lines)[:MAX_EVIDENCE_CHARS]


def save_grade(pool: ConnectionPool, claim_id: str, grade: FeatureGrade) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE results SET feature_score = %s, score_reason = %s, score_breakdown = %s::jsonb WHERE claim_id = %s::uuid",
                     (grade.score, grade.reason, json.dumps(grade.breakdown), claim_id))


def _grade(sv, info: SubjectInfo, claim: Claim, checklist: Optional[dict], job_id: str) -> tuple[Optional[FeatureGrade], str]:
    """(grade, confidence). A claim whose grading fails is simply not scored this time."""
    try:
        verdict, confidence, _reason, evidence = evidence_text(sv.pool, claim.id)
        grade = grade_feature(sv.model, claim.text, claim.claim_group, info.role_level, verdict, evidence,
                              checklist=Checklist.model_validate(checklist) if checklist else None, job_id=job_id)
        save_grade(sv.pool, claim.id, grade)
        return grade, confidence
    except Exception as err:
        log.warning("could not score claim %s: %s", claim.id, err)
        return None, "low"


@stage("feature_score")
def feature_score(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    sv = get_services(ctx.pool)
    info = load_subject_info(ctx.pool, subject_of(job))
    set_status(ctx.pool, info, "scoring")
    claims = load_claims(ctx.pool, info.subject, testable_only=True)
    if not claims:
        return {"skipped": True, "reason": "there are no testable claims"}
    with ctx.pool.connection() as conn:
        tested = {r[0] for r in conn.execute("SELECT claim_id::text FROM results WHERE claim_id = ANY(%s::uuid[])",
                                             ([c.id for c in claims],)).fetchall()}
    # Checklists were written before any test ran: by sandbox_plan for backend claims, by test_plan for live ones.
    checklists = {**((stage_result(ctx.pool, job, "sandbox_plan") or {}).get("checklists") or {}),
                  **((stage_result(ctx.pool, job, "test_plan") or {}).get("claims") or {})}
    to_grade = [c for c in claims if c.id in tested]
    with ThreadPoolExecutor(max_workers=GRADING_THREADS) as threads:
        grades = dict(zip([c.id for c in to_grade], threads.map(
            lambda c: _grade(sv, info, c, (checklists.get(c.id) or {}).get("checklist"), job.id), to_grade)))
    ctx.check()

    items = []
    for c in claims:
        grade, confidence = grades.get(c.id, (None, "low"))
        items.append(FeatureItem(importance=c.importance, score=grade.score if grade else None, testable=True,
                                 confidence=confidence))
    total = talnex_score(items)
    save_talnex_score(ctx.pool, info.kind, info.id, total)
    return {"features_scored": total.features_used, "of": len(claims), "talnex_score": total.score10,
            "coverage": total.coverage, "low_coverage": total.low_coverage,
            "not_scored": [c.text for c, item in zip(claims, items) if item.score is None]}
