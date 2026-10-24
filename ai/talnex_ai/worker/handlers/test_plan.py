"""Stage `test_plan`: for every testable claim, write the test plans AND the scoring checklist.

The checklist is written here, before any test has run, so the feature score later rests on a list
made without seeing the results. Plans and checklists are saved in this job's result; `live_test`
and `feature_score` read them. A claim that can't be planned is recorded with the reason and ends
up "could not test", never "broken".
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Optional, Sequence

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim
from talnex_ai.llm.structured import ChatClient
from talnex_ai.scoring.talnex_score.checklist import write_checklist
from talnex_ai.testing.planner.planner import plan_claim
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import SubjectInfo, load_subject_info, stage_result, subject_of

log = logging.getLogger("talnex.test_plan")

PLANNING_THREADS = 4


def code_hint(note: Mapping[str, Any]) -> str:
    """What reading the code said about a claim: how a visitor reaches the feature, and where it is."""
    parts = []
    if note.get("how_to_try"):
        parts.append(f"How a visitor reaches it, from reading the code: {note['how_to_try']}")
    if note.get("needs_login"):
        parts.append("The code puts this behind a sign-in.")
    where = "; ".join(f"{e.get('file')}:{e.get('line')}" for e in (note.get("evidence") or [])[:3] if e.get("file"))
    if where:
        parts.append(f"Code: {where}")
    return "\n".join(parts)


def plan_one(model: ChatClient, info: SubjectInfo, claim: Claim, job_id: Optional[str],
             note: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Plans and a checklist for one claim. A failure is recorded, never raised, so other claims still get planned."""
    try:
        plans = plan_claim(model, claim, site_url=info.live_url or "", site_notes=code_hint(note or {}) or None,
                           job_id=job_id)
        checklist = write_checklist(model, claim.text, claim.claim_group, info.role_level, job_id=job_id)
        return {"plans": [p.model_dump() for p in plans], "checklist": checklist.model_dump()}
    except Exception as err:
        log.warning("could not plan claim %s: %s", claim.id, err)
        return {"error": f"a test could not be planned ({type(err).__name__})"}


def plan_subject(model: ChatClient, info: SubjectInfo, claims: Sequence[Claim], job_id: Optional[str],
                 notes: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Plan every claim of one subject, a few at a time."""
    notes = notes or {}
    with ThreadPoolExecutor(max_workers=PLANNING_THREADS) as threads:
        planned = list(threads.map(lambda c: plan_one(model, info, c, job_id, notes.get(c.text)), claims))
    return {"site_url": info.live_url, "claims": {c.id: p for c, p in zip(claims, planned)}}


@stage("test_plan")
def test_plan(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    claims = load_claims(ctx.pool, subject, testable_only=True)
    if not claims:
        return {"skipped": True, "reason": "there are no testable claims"}
    if not info.live_url:
        return {"skipped": True, "reason": "no live link was given"}
    live = (stage_result(ctx.pool, job, "precheck") or {}).get("live")
    if live is not None and not live.get("ok"):
        return {"skipped": True, "reason": f"the live link did not load ({live.get('error_code') or 'no answer'})"}

    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    notes = (stage_result(ctx.pool, job, "claims") or {}).get("notes") or {}
    result = plan_subject(get_services(ctx.pool).model, info, claims, job.id, notes)
    ctx.check()
    return result
