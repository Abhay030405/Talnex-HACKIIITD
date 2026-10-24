"""Saves test runs and their steps. Go owns the schema; this only writes rows."""
from __future__ import annotations

import json

from typing import Optional

from psycopg_pool import ConnectionPool

from talnex_ai.formats import StepRecord

RUN_OUTCOMES = ("passed", "failed", "blocked", "error")  # what the database allows


def create_run(pool: ConnectionPool, claim_id: str, try_number: int, test_type: str, *, track: str = "live",
               method: Optional[str] = None) -> str:
    with pool.connection() as conn:
        return conn.execute(
            """INSERT INTO test_runs (claim_id, try_number, track, test_type, method, started_at)
               VALUES (%s::uuid, %s, %s, %s, %s, now()) RETURNING id::text""",
            (claim_id, try_number, track, test_type, method),
        ).fetchone()[0]


def add_steps(pool: ConnectionPool, run_id: str, steps: list[StepRecord]) -> None:
    """Save a run's steps in one transaction. Saving again replaces them, so a retry leaves no duplicates."""
    if not steps:
        return
    with pool.connection() as conn, conn.transaction():
        for s in steps:
            conn.execute(
                """INSERT INTO steps (run_id, step_number, kind, action, expected, observed, proof_key, duration_ms, devtools)
                   VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (run_id, step_number) DO UPDATE SET
                       action = EXCLUDED.action, expected = EXCLUDED.expected, observed = EXCLUDED.observed,
                       proof_key = EXCLUDED.proof_key, duration_ms = EXCLUDED.duration_ms, devtools = EXCLUDED.devtools""",
                (run_id, s.step_number, s.kind, s.action, s.expected, s.observed, s.proof_key, s.duration_ms,
                 json.dumps(s.devtools) if s.devtools is not None else None),
            )


def finish_run(pool: ConnectionPool, run_id: str, outcome: str) -> None:
    if outcome not in RUN_OUTCOMES:
        raise ValueError(f"unknown run outcome {outcome!r}")
    with pool.connection() as conn:
        conn.execute("UPDATE test_runs SET ended_at = now(), outcome = %s WHERE id = %s::uuid", (outcome, run_id))


def load_steps(pool: ConnectionPool, run_id: str) -> list[StepRecord]:
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT step_number, kind, action, expected, observed, proof_key, duration_ms, devtools
                 FROM steps WHERE run_id = %s::uuid ORDER BY step_number""", (run_id,)).fetchall()
    fields = ("step_number", "kind", "action", "expected", "observed", "proof_key", "duration_ms", "devtools")
    return [StepRecord(**dict(zip(fields, row))) for row in rows]
