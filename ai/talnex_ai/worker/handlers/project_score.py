"""Stage `project_score`: a hackathon project's group scores, plus the weighted total for fixed-problem events.

It reads the results the testing stages saved. Only what was actually tested counts: "could not
test" is left out of every score and listed instead, and red flags are never subtracted. The AI
opinion is never part of a score. It sets the final status: done, or done with gaps when something
couldn't be tested.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from talnex_ai.claims.criteria import load_brief
from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.scoring.store import save_group_score, save_weighted_total
from talnex_ai.scoring.talnex_score import ClaimOutcome, CriterionGroup, group_score, weighted_total
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import load_subject_info, set_status, subject_of


@stage("project_score")
def project_score(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    if subject.kind != "project":
        return {"skipped": True, "reason": "group scores are for hackathon projects"}
    info = load_subject_info(ctx.pool, subject)
    set_status(ctx.pool, info, "scoring")

    claims = load_claims(ctx.pool, subject)
    results = {}
    if claims:
        with ctx.pool.connection() as conn:
            rows = conn.execute("""SELECT claim_id::text, verdict, confidence, feature_score
                                     FROM results WHERE claim_id = ANY(%s::uuid[])""", ([c.id for c in claims],))
            results = {claim_id: rest for claim_id, *rest in rows.fetchall()}

    by_group: dict[str, list[ClaimOutcome]] = defaultdict(list)
    not_tested: list[str] = []
    for c in claims:
        verdict, confidence, feature_score = results.get(c.id, ("could_not_test", "low", None))
        # A claim judged only from its code counts by its feature score (already capped at 7 out of 10).
        override = float(feature_score) / 10 if verdict == "reviewed_from_code" and feature_score is not None else None
        by_group[c.claim_group].append(ClaimOutcome(c.importance, verdict, confidence, c.testable, override))
        if c.testable and verdict in ("could_not_test", "reviewed_from_code"):
            not_tested.append(c.text)

    scores = {name: group_score(outcomes) for name, outcomes in by_group.items()}
    for name, g in scores.items():
        save_group_score(ctx.pool, "project", subject.id, name, g)
    result: dict[str, Any] = {"groups": {n: g.score for n, g in scores.items()}, "not_tested": not_tested}

    brief = load_brief(ctx.pool, subject.id)
    if brief is not None and brief.mode == "fixed_problem" and brief.criteria:
        # One entry per criterion, even one with nothing tested: it's left out, the rest rescaled, and it says so.
        total = weighted_total(CriterionGroup(c.weight, scores.get(c.name) or group_score([])) for c in brief.criteria)
        save_weighted_total(ctx.pool, subject.id, total)
        result["weighted_total"] = {"score": total.score, "weight_covered": total.weight_covered,
                                    "criteria_used": total.criteria_used, "criteria_total": total.criteria_total}

    set_status(ctx.pool, info, "done_with_gaps" if not_tested else "done")
    return result
