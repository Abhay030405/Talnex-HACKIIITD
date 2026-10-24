"""Stage `track_reconcile`: when the live site and the repository tests both tried the same claim, they must agree.

Architecture 28.1: when both tracks test the same claim and disagree, the result is "could not
confirm", never "broken". Works for a hackathon project and a resume project alike, and only looks at
claims whose track is `both`.

The saved result belongs to whichever track wrote last, so the other track is read from its test runs:
  - "good" when any of its runs passed,
  - "bad" when it ran at least twice and none passed (the ladder tries a failing claim twice before
    calling it broken),
  - otherwise "unknown", which says nothing.
A works or partly-works result with the other track bad, or a broken result with the other track
good, becomes "could not test" with the reason. Everything else stays as it is.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Result
from talnex_ai.scoring.store import save_result
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import subject_of

# A repository run is saved as "passed" even when some of its steps failed (partly works), so it only
# counts as a pass when none of its steps failed: a route that answered 500 is not the repo agreeing.
_RUNS = """
SELECT r.track,
       CASE WHEN r.outcome = 'passed' AND r.track = 'sandbox'
                 AND EXISTS (SELECT 1 FROM steps s WHERE s.run_id = r.id AND s.observed ILIKE 'fail%%')
            THEN 'failed' ELSE r.outcome END
  FROM test_runs r WHERE r.claim_id = %s::uuid
"""


def track_state(outcomes: list[str]) -> str:
    """good / bad / unknown for one track, from the outcomes of its runs."""
    if "passed" in outcomes:
        return "good"
    if outcomes.count("failed") >= 2 and all(o in ("failed", "blocked", "error") for o in outcomes):
        return "bad"
    return "unknown"


def reconcile(verdict: str, live: str, sandbox: str) -> tuple[bool, str]:
    """(conflict, reason): whether the two tracks contradict each other, given the saved verdict and each track's state."""
    states = {"live site": live, "repository tests": sandbox}
    good = [name for name, state in states.items() if state == "good"]
    bad = [name for name, state in states.items() if state == "bad"]
    if verdict in ("works", "partly_works") and bad:
        return True, f"the {good[0] if good else 'one check'} passed but the {bad[0]} failed, so it is not confirmed"
    if verdict == "broken" and good:
        return True, f"the {bad[0] if bad else 'one check'} failed but the {good[0]} passed, so it is not confirmed"
    return False, ""


@stage("track_reconcile")
def track_reconcile(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    claims = [c for c in load_claims(ctx.pool, subject, testable_only=True) if c.track == "both" and c.id]
    if not claims:
        return {"skipped": True, "reason": "no claim was tested by both the live site and the repository"}
    changed = 0
    for claim in claims:
        with ctx.pool.connection() as conn:
            result = conn.execute("SELECT verdict FROM results WHERE claim_id = %s::uuid", (claim.id,)).fetchone()
            runs = conn.execute(_RUNS, (claim.id,)).fetchall()
        if result is None:
            continue
        live = track_state([o for track, o in runs if track == "live" and o])
        sandbox = track_state([o for track, o in runs if track == "sandbox" and o])
        conflict, reason = reconcile(result[0], live, sandbox)
        if conflict:
            save_result(ctx.pool, Result(claim_id=claim.id, verdict="could_not_test", confidence="disagree", reason=reason))
            changed += 1
    return {"checked": len(claims), "disagreed": changed}
