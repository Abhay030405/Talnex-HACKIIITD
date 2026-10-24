"""Python side of the job queue.

The queue rules live in Postgres functions (backend/migrations), so the Go and Python workers
share one implementation: row locking so two workers never take the same job, retries with a
growing delay, and adding the next pipeline stages in the same transaction that marks a job
done. This module only calls those functions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

RUNNER_PYTHON = "python"
RUNNER_GO = "go"


@dataclass(frozen=True)
class Job:
    id: str
    type: str
    runner: str
    target_type: str
    target_id: str
    input: dict
    pipeline: Optional[str]
    run_number: int
    tries: int
    max_tries: int
    time_limit_seconds: int

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Job":
        return cls(
            id=str(row["id"]),
            type=row["job_type"],
            runner=row["runner"],
            target_type=row["target_type"],
            target_id=str(row["target_id"]),
            input=dict(row["input"] or {}),
            pipeline=row["pipeline"],
            run_number=row["run_number"],
            tries=row["tries"],
            max_tries=row["max_tries"],
            time_limit_seconds=row["time_limit_seconds"],
        )


def _value(pool: ConnectionPool, sql: str, params: tuple) -> Any:
    with pool.connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _ids(pool: ConnectionPool, sql: str, params: tuple) -> list[str]:
    with pool.connection() as conn:
        return [str(r[0]) for r in conn.execute(sql, params).fetchall()]


def take_job(pool: ConnectionPool, runner: str, worker: str) -> Optional[Job]:
    """Lock and return the next free job for this runner, or None if there is nothing to do."""
    with pool.connection() as conn:
        # dict rows only on this cursor: setting it on the pooled connection would leak to the next user.
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT * FROM take_job(%s, %s)", (runner, worker)).fetchone()
    return Job.from_row(row) if row else None


def complete_job(pool: ConnectionPool, job_id: str, worker: str,
                 result: Optional[Mapping[str, Any]] = None) -> list[str]:
    """Save the result, mark the job done and queue the stages that were waiting on it.

    Returns the ids of the newly queued jobs. Returns nothing if this worker no longer holds the job
    (for example it ran past its time limit and was taken back)."""
    return _ids(pool, "SELECT x FROM complete_job(%s::uuid, %s, %s::jsonb) AS x",
                (job_id, worker, json.dumps(result or {})))


def fail_job(pool: ConnectionPool, job_id: str, worker: str, message: str,
             delay_seconds: int = 30) -> Optional[str]:
    """Record a failure. Returns 'retrying' or 'failed', or None if this worker no longer holds the job."""
    return _value(pool, "SELECT fail_job(%s::uuid, %s, %s, %s)", (job_id, worker, message, delay_seconds))


def enqueue_job(
    pool: ConnectionPool,
    job_type: str,
    runner: str,
    target_type: str,
    target_id: str,
    *,
    input: Optional[Mapping[str, Any]] = None,
    pipeline: Optional[str] = None,
    run_number: int = 1,
    time_limit_seconds: int = 900,
    max_tries: int = 3,
) -> Optional[str]:
    """Add one job. Returns its id, or None when the same job (same pipeline, stage, target and run) exists."""
    job_id = _value(
        pool,
        "SELECT enqueue_job(%s, %s, %s, %s::uuid, %s::jsonb, %s, %s, %s, %s)",
        (job_type, runner, target_type, target_id, json.dumps(input or {}), pipeline,
         run_number, time_limit_seconds, max_tries),
    )
    return str(job_id) if job_id else None


def start_pipeline(pool: ConnectionPool, pipeline: str, target_type: str, target_id: str,
                   run_number: int = 1) -> list[str]:
    """Queue every first stage of a pipeline for one target. Returns the new job ids."""
    return _ids(pool, "SELECT x FROM start_pipeline(%s, %s, %s::uuid, %s) AS x",
                (pipeline, target_type, target_id, run_number))
