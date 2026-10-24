"""Stage `feature_compare` (event level): "these teams built this feature best" (top 3, never one winner).

The model only groups claims that are the same feature across teams; the order is plain code
(scoring/feature_compare). Open-theme events also get "Best Access / Core / Logic / Reliability".
Results replace the earlier ones for the event.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.db.jobs import Job
from talnex_ai.llm.structured import ChatClient
from talnex_ai.scoring.feature_compare import Entry, best_by_group, best_teams, eligible, group_by_meaning
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall

# One row per claim with a result, plus the number of steps in its best run (a passed run first, then the latest try).
_ENTRIES = """
SELECT c.id::text, p.id::text, p.team_name, c.claim_group, c.text, r.verdict, r.confidence, r.feature_score::float8,
       coalesce(r.reason, ''), r.proof_keys,
       coalesce((SELECT count(*) FROM steps s
                  WHERE s.run_id = (SELECT tr.id FROM test_runs tr WHERE tr.claim_id = c.id
                                     ORDER BY (tr.outcome = 'passed') DESC, tr.try_number DESC LIMIT 1)), 0)
  FROM claims c JOIN results r ON r.claim_id = c.id JOIN projects p ON p.id = c.project_id
 WHERE p.event_id = %s::uuid ORDER BY c.claim_group, p.team_name, c.id
"""
NOTE = "Top 3 per feature, never one winner. Could-not-test and broken claims are not part of the comparison."


def compare_event(pool: ConnectionPool, model: ChatClient, event_id: str, *, job_id: Optional[str] = None,
                  check: Callable[[], None] = lambda: None) -> dict[str, Any]:
    with pool.connection() as conn:
        mode = conn.execute("SELECT mode FROM events WHERE id = %s::uuid", (event_id,)).fetchone()[0]
        rows = conn.execute(_ENTRIES, (event_id,)).fetchall()
        score_rows = conn.execute("""SELECT s.project_id::text, s.score_group, s.score::float8, s.coverage::float8
                                       FROM scores s JOIN projects p ON p.id = s.project_id
                                      WHERE p.event_id = %s::uuid""", (event_id,)).fetchall()
        names = dict(conn.execute("SELECT id::text, team_name FROM projects WHERE event_id = %s::uuid", (event_id,)).fetchall())
    coverage = {pid: cov for pid, group, _score, cov in score_rows if group == "talnex"}
    entries = [Entry(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], int(r[10]), r[8], list(r[9] or [])) for r in rows]
    compared = eligible(entries, coverage)
    if len({e.project_id for e in compared}) < 2:
        return {"skipped": True, "reason": "fewer than two teams have enough tested features to compare"}

    groups: list[tuple[str, str, list[dict], list[str]]] = []  # (kind, name, best teams, claim ids)
    by_claim_group: dict[str, list[Entry]] = {}
    for e in compared:
        by_claim_group.setdefault(e.group, []).append(e)
    for members in by_claim_group.values():
        if len({m.project_id for m in members}) < 2:
            continue
        for name, found in group_by_meaning(model, members, job_id=job_id):
            groups.append(("feature", name, best_teams(found), [e.claim_id for e in found]))
        check()
    if mode == "open_theme":
        scores: dict[str, dict[str, tuple]] = {}
        for pid, group, score, cov in score_rows:
            scores.setdefault(group, {})[pid] = (score, cov)
        groups += [("group", name, best, []) for name, best in best_by_group(scores, names)]

    with pool.connection() as conn, conn.transaction():
        conn.execute("DELETE FROM feature_groups WHERE event_id = %s::uuid", (event_id,))
        for kind, name, best, claim_ids in groups:
            conn.execute("""INSERT INTO feature_groups (event_id, feature_name, claim_ids, best_teams, kind)
                            VALUES (%s::uuid, %s, %s::uuid[], %s::jsonb, %s)""",
                         (event_id, name, claim_ids, json.dumps(best), kind))
    return {"teams": len({e.project_id for e in compared}),
            "features": sum(1 for g in groups if g[0] == "feature"),
            "group_bests": sum(1 for g in groups if g[0] == "group"), "note": NOTE}


@stage("feature_compare")
@never_stall
def feature_compare(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    if job.target_type != "event":
        return {"skipped": True, "reason": "this check works on a whole event"}
    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    return compare_event(ctx.pool, get_services(ctx.pool).model, job.target_id, job_id=job.id, check=ctx.check)
