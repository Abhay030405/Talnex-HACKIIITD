"""How long a check took and what it cost, for the proof card and the recruiter report.

Measured from what is already recorded: each subject's latest run of jobs (first job created to last job ended) and
the `usage_log` cost of every model call and browser session those jobs made. Model and browser costs are shown
apart, so an organizer can see where the money goes. A run still going reports the time so far.
"""
from __future__ import annotations

from typing import Optional, Sequence

# A target is (target_type, id), as in the jobs table: ("project", id), ("candidate", id), ("candidate_project", id).
Target = tuple[str, str]

_JOBS = """
WITH targets AS (SELECT * FROM unnest(%(kinds)s::text[], %(ids)s::uuid[]) AS t(kind, id)),
     latest AS (SELECT j.target_type, j.target_id, max(j.run_number) AS run
                  FROM jobs j JOIN targets t ON t.kind = j.target_type AND t.id = j.target_id
                 GROUP BY j.target_type, j.target_id)
SELECT j.id FROM jobs j JOIN latest l
    ON l.target_type = j.target_type AND l.target_id = j.target_id AND l.run = j.run_number
"""


def run_usage(conn, targets: Sequence[Target]) -> Optional[dict]:
    """Time and cost of the latest run of these targets together, or None when they never ran."""
    if not targets:
        return None
    params = {"kinds": [k for k, _ in targets], "ids": [i for _, i in targets]}
    row = conn.execute(
        f"""WITH run_jobs AS ({_JOBS})
            SELECT min(j.created_at), max(j.updated_at),
                   count(*) FILTER (WHERE j.status IN ('queued', 'running', 'retrying'))
              FROM jobs j WHERE j.id IN (SELECT id FROM run_jobs)""", params).fetchone()
    first, last, still_open = row
    if first is None:
        return None
    usage = conn.execute(
        f"""WITH run_jobs AS ({_JOBS})
            SELECT coalesce(sum(u.cost_usd) FILTER (WHERE u.service NOT LIKE 'tinyfish%%'), 0)::float8,
                   coalesce(sum(u.cost_usd) FILTER (WHERE u.service LIKE 'tinyfish%%'), 0)::float8,
                   count(*) FILTER (WHERE u.service NOT LIKE 'tinyfish%%'),
                   count(*) FILTER (WHERE u.service LIKE 'tinyfish%%')
              FROM usage_log u WHERE u.job_id IN (SELECT id FROM run_jobs)""", params).fetchone()
    model_usd, browser_usd, model_calls, browser_sessions = usage
    return {
        "seconds": max(0, round((last - first).total_seconds())),
        "finished": still_open == 0,
        "cost_usd": round(model_usd + browser_usd, 4),
        "model_usd": round(model_usd, 4),
        "browser_usd": round(browser_usd, 4),
        "model_calls": model_calls,
        "browser_sessions": browser_sessions,
    }
