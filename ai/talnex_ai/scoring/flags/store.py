"""Saving red flags. A flag sits BESIDE the score and is never subtracted from it (AGENTS.md rule 4).

The same flag isn't saved twice, so stages can run again (a retry or a re-run) without piling up
copies. If it's found again at a stronger level, the saved one is raised to that level.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

from psycopg_pool import ConnectionPool

Level = Literal["info", "review", "strong"]
LEVEL_RANK = {"info": 1, "review": 2, "strong": 3}
_COLUMN = {"project": "project_id", "candidate_project": "candidate_project_id", "candidate": "candidate_id"}


def add_flag(
    pool: ConnectionPool,
    kind: str,
    subject_id: str,
    flag_type: str,
    level: Level,
    reason: str,
    evidence: Optional[dict] = None,
) -> bool:
    """Save a flag unless the same one (same type and reason) is already there.

    Returns True when something changed: the flag was added, or an existing one was raised to a
    stronger level (taking the new evidence with it)."""
    if level not in LEVEL_RANK:
        raise ValueError(f"unknown flag level {level!r}")
    column = _COLUMN[kind]  # one of three fixed names, never outside input
    with pool.connection() as conn, conn.transaction():
        # Claims are tested in parallel and can find the same thing at the same moment. This lock
        # makes them take turns per flag, so it's saved once. The pool's connections are in
        # autocommit mode, so the explicit transaction is what holds the lock until the insert.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                     (f"flag:{subject_id}:{flag_type}:{reason}",))
        row = conn.execute(
            f"SELECT id, level FROM flags WHERE {column} = %s::uuid AND flag_type = %s AND reason = %s",
            (subject_id, flag_type, reason),
        ).fetchone()
        if row is None:
            conn.execute(
                f"""INSERT INTO flags ({column}, flag_type, level, reason, evidence)
                    VALUES (%s::uuid, %s, %s, %s, %s::jsonb)""",
                (subject_id, flag_type, level, reason, json.dumps(evidence or {})),
            )
            return True
        flag_id, saved_level = row
        if LEVEL_RANK[level] > LEVEL_RANK[saved_level]:
            conn.execute("UPDATE flags SET level = %s, evidence = %s::jsonb WHERE id = %s",
                         (level, json.dumps(evidence or {}), flag_id))
            return True
    return False
