"""Saving coding-profile signals. One row per candidate, site and signal; running a stage twice replaces the row."""
from __future__ import annotations

import json
from typing import Any, Mapping

from psycopg_pool import ConnectionPool

SITES = ("codeforces", "leetcode", "codechef")


def save_signal(pool: ConnectionPool, candidate_id: str, site: str, signal: str, evidence: Mapping[str, Any],
                weight: str = "not_suspicious") -> None:
    """Replace the (candidate, site, signal) row with this one, in one transaction (safe to run twice)."""
    if site not in SITES:
        raise ValueError(f"unknown coding site {site!r}")
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM coding_signals WHERE candidate_id = %s::uuid AND site = %s AND signal = %s",
                         (candidate_id, site, signal))
            conn.execute(
                """INSERT INTO coding_signals (candidate_id, site, signal, weight, evidence)
                   VALUES (%s::uuid, %s, %s, %s, %s::jsonb)""",
                (candidate_id, site, signal, weight, json.dumps(dict(evidence))),
            )


def clear_signal(pool: ConnectionPool, candidate_id: str, site: str, signal: str) -> None:
    """Remove an old row, for when a re-run finds the profile can no longer be read (stale facts must not stay)."""
    with pool.connection() as conn:
        conn.execute("DELETE FROM coding_signals WHERE candidate_id = %s::uuid AND site = %s AND signal = %s",
                     (candidate_id, site, signal))
