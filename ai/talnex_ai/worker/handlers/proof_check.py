"""Stage `proof_check`: make sure every testable claim ended with a result.

The independent proof check itself runs inside `live_test`, because the never-blame ladder needs it
between tries. This stage is the safety net after it: a claim that somehow has no result (a crashed
worker, a skipped stage) gets an honest "could not test" with the reason, so the report never has a
silent gap and nobody is blamed for our trouble.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Result
from talnex_ai.scoring.store import save_result
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import load_subject_info, set_status, subject_of

GAP_REASON = "not tested: the test did not finish"


@stage("proof_check")
def proof_check_stage(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    set_status(ctx.pool, load_subject_info(ctx.pool, subject), "checking")

    claims = load_claims(ctx.pool, subject, testable_only=True)
    have: set[str] = set()
    if claims:
        with ctx.pool.connection() as conn:
            rows = conn.execute("SELECT claim_id::text FROM results WHERE claim_id = ANY(%s::uuid[])",
                                ([c.id for c in claims],)).fetchall()
        have = {r[0] for r in rows}

    gaps = [c for c in claims if c.id not in have]
    for claim in gaps:
        save_result(ctx.pool, Result(claim_id=claim.id, verdict="could_not_test", confidence="low", reason=GAP_REASON))
    return {"claims": len(claims), "with_results": len(claims) - len(gaps), "filled_in": len(gaps)}
