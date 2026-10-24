"""The usage log: one row per model call or agent run, so every result can show its time and cost."""
from __future__ import annotations

import logging
from typing import Optional

import psycopg
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)


def log_usage(
    pool: ConnectionPool,
    *,
    service: str,
    model: Optional[str] = None,
    job_id: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    duration_ms: Optional[int] = None,
    cost_usd: Optional[float] = None,
) -> bool:
    """Write one usage row. Returns False instead of raising if the write fails.

    By the time we log, the model call has already happened and been paid for, so a failed
    write must not throw that answer away and fail the job."""
    try:
        with pool.connection() as conn:
            conn.execute(
                """INSERT INTO usage_log (job_id, service, model, tokens_in, tokens_out, duration_ms, cost_usd)
                   VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)""",
                (job_id, service, model, tokens_in, tokens_out, duration_ms, cost_usd),
            )
    except psycopg.Error as err:
        log.warning("could not write usage row for %s (%s): %s", service, model, err)
        return False
    return True
