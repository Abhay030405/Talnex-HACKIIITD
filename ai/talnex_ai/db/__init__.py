"""Database access for the AI worker.

Go owns the schema (backend/migrations). Python reads and writes the same tables but never
changes their shape.
"""
from __future__ import annotations

from psycopg_pool import ConnectionPool, PoolTimeout


def open_pool(database_url: str, max_size: int = 10) -> ConnectionPool:
    """Open a pool of autocommit connections and fail fast if the database doesn't answer."""
    pool = ConnectionPool(database_url, min_size=1, max_size=max_size, open=False,
                          kwargs={"autocommit": True})
    try:
        pool.open(wait=True, timeout=15)
    except PoolTimeout:
        pool.close()
        # The URL holds the password, so it never goes into the message.
        raise RuntimeError("could not reach the database within 15 seconds; check DATABASE_URL") from None
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return pool
