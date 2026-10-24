"""Reads and writes `claim_code_maps` and `authorship`. Go owns the tables; this only writes rows. Every write replaces what a
claim had before, so running a stage twice leaves one set of rows."""
from __future__ import annotations

import json
from typing import Iterable, Optional, Sequence

from psycopg_pool import ConnectionPool

from talnex_ai.checks.authorship.locate import CodeMap
from talnex_ai.checks.authorship.read import ClaimAuthorship

FLAG_TYPES = ("feature_one_drop", "feature_before_event", "claimed_by_other_account", "reformatting_hides_authorship")
_FLAG_COLUMN = {"project": "project_id", "candidate_project": "candidate_project_id"}


def save_code_maps(pool: ConnectionPool, maps: Iterable[CodeMap]) -> None:
    """One row per claim. The commit is cleared: the history stage after this one sets it for the new map."""
    with pool.connection() as conn, conn.transaction():
        for m in maps:
            conn.execute(
                """INSERT INTO claim_code_maps (claim_id, commit_sha, files, found_by, confidence, not_traced_reason)
                   VALUES (%s::uuid, NULL, %s::jsonb, %s, %s, %s)
                   ON CONFLICT (claim_id) DO UPDATE SET commit_sha = NULL, files = EXCLUDED.files, found_by = EXCLUDED.found_by,
                       confidence = EXCLUDED.confidence, not_traced_reason = EXCLUDED.not_traced_reason, created_at = now()""",
                (m.claim_id, json.dumps(m.files), m.found_by, m.confidence, m.not_traced_reason))


def load_code_maps(pool: ConnectionPool, claim_ids: Sequence[str]) -> dict[str, dict]:
    """claim id -> {"files", "commit_sha", "not_traced_reason", "found_by", "confidence"} for the claims that have a map."""
    if not claim_ids:
        return {}
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT claim_id::text, files, commit_sha, not_traced_reason, found_by, confidence FROM claim_code_maps
                WHERE claim_id = ANY(%s::uuid[])""", (list(claim_ids),)).fetchall()
    return {r[0]: {"files": r[1] or [], "commit_sha": r[2], "not_traced_reason": r[3], "found_by": r[4], "confidence": r[5]}
            for r in rows}


def set_not_traced(pool: ConnectionPool, claim_id: str, reason: str) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE claim_code_maps SET not_traced_reason = %s WHERE claim_id = %s::uuid", (reason, claim_id))


def replace_authorship(pool: ConnectionPool, claim_ids: Sequence[str], results: Iterable[ClaimAuthorship]) -> int:
    """Delete the claims' rows and write the new ones in one step. Returns how many rows were written."""
    written = 0
    with pool.connection() as conn, conn.transaction():
        conn.execute("DELETE FROM authorship WHERE claim_id = ANY(%s::uuid[])", (list(claim_ids),))
        for ca in results:
            for a in ca.accounts:
                conn.execute(
                    """INSERT INTO authorship (claim_id, account, line_share, lines, commits, days_spanned, largest_commit_share,
                                               first_pushed_at, last_pushed_at, date_source, reformatted_lines, moved_lines)
                       VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (ca.claim_id, a.account, a.line_share, a.lines, a.commits, a.days_spanned, a.largest_commit_share,
                     a.first_pushed_at, a.last_pushed_at, a.date_source, a.reformatted_lines, a.moved_lines))
                written += 1
    return written


def clear_flags(pool: ConnectionPool, kind: str, subject_id: str) -> None:
    """Remove this stage's earlier flags for a subject, so a re-run with new numbers does not leave the old ones beside them."""
    with pool.connection() as conn:
        conn.execute(f"DELETE FROM flags WHERE {_FLAG_COLUMN[kind]} = %s::uuid AND flag_type = ANY(%s)", (subject_id, list(FLAG_TYPES)))


def authorship_rows(conn, claim_id: str) -> list[dict]:
    """The saved rows of one claim, biggest share first (for the reports). Takes an open connection."""
    return [{"account": acc, "line_share": float(share), "lines": lines, "commits": commits, "days_spanned": days,
             "largest_commit_share": None if largest is None else float(largest),
             "first_pushed_at": first.isoformat() if first else None, "last_pushed_at": last.isoformat() if last else None,
             "date_source": source, "reformatted_lines": reformatted, "moved_lines": moved}
            for acc, share, lines, commits, days, largest, first, last, source, reformatted, moved in conn.execute(
                """SELECT account, line_share, lines, commits, days_spanned, largest_commit_share, first_pushed_at, last_pushed_at,
                          date_source, reformatted_lines, moved_lines
                     FROM authorship WHERE claim_id = %s::uuid ORDER BY line_share DESC, lower(account)""", (claim_id,))]


def code_map_row(conn, claim_id: str) -> Optional[dict]:
    row = conn.execute("SELECT files, commit_sha, not_traced_reason FROM claim_code_maps WHERE claim_id = %s::uuid", (claim_id,)).fetchone()
    return {"files": row[0] or [], "commit_sha": row[1], "not_traced_reason": row[2]} if row else None
