"""Reads and writes `sandbox_runs`, one row per attempt to run a repo in a VM. Go owns the table; this only writes rows.

The row holds the recipe, where the app is listening and which VM it lives in, so later stages (route discovery, API
tests, repo tests) can find the running app without asking the earlier stage."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from talnex_ai.claims.store import Subject

STATUSES = ("pending", "building", "running", "done", "could_not_run", "failed")
_FIELDS = {"recipe", "image", "status", "status_detail", "build_log_key", "run_log_key", "resources"}
_JSON = {"recipe", "resources"}


@dataclass(frozen=True)
class SandboxRun:
    id: str
    status: str
    status_detail: Optional[str]
    recipe: dict
    image: Optional[str]
    resources: dict
    build_log_key: Optional[str]
    run_log_key: Optional[str]

    @property
    def vm_id(self) -> Optional[str]:
        return self.resources.get("vm_id")

    @property
    def port(self) -> Optional[int]:
        return self.resources.get("port")


def create_run(pool: ConnectionPool, subject: Subject) -> str:
    with pool.connection() as conn:
        return conn.execute(
            f"INSERT INTO sandbox_runs ({subject.column}, status, started_at) VALUES (%s::uuid, 'pending', now()) RETURNING id::text",
            (subject.id,),
        ).fetchone()[0]


def update_run(pool: ConnectionPool, run_id: str, *, ended: bool = False, **fields: Any) -> None:
    """Change some columns of a run. `recipe` and `resources` are saved as JSON; `resources` is merged into what is there."""
    unknown = set(fields) - _FIELDS
    if unknown:
        raise ValueError(f"unknown sandbox_runs fields: {sorted(unknown)}")
    if fields.get("status") is not None and fields["status"] not in STATUSES:
        raise ValueError(f"unknown sandbox run status {fields['status']!r}")
    sets, args = [], []
    for name, value in fields.items():
        if name == "resources":
            sets.append("resources = resources || %s::jsonb")
            args.append(json.dumps(value))
        elif name in _JSON:
            sets.append(f"{name} = %s::jsonb")
            args.append(json.dumps(value))
        else:
            sets.append(f"{name} = %s")
            args.append(value)
    if ended:
        sets.append("ended_at = now()")
    if not sets:
        return
    with pool.connection() as conn:
        conn.execute(f"UPDATE sandbox_runs SET {', '.join(sets)} WHERE id = %s::uuid", (*args, run_id))


def latest_run(pool: ConnectionPool, subject: Subject) -> Optional[SandboxRun]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""SELECT id::text AS id, status, status_detail, recipe, image, resources, build_log_key, run_log_key
                      FROM sandbox_runs WHERE {subject.column} = %s::uuid ORDER BY created_at DESC LIMIT 1""",
                (subject.id,),
            ).fetchone()
    return SandboxRun(**row) if row else None


def save_code_review(pool: ConnectionPool, run_id: str, claim_id: str, finding: dict) -> None:
    """Keep one claim's code-review finding with the run, under resources.code_review[claim_id]."""
    with pool.connection() as conn:
        conn.execute(
            """UPDATE sandbox_runs
                  SET resources = jsonb_set(resources, '{code_review}',
                                            coalesce(resources->'code_review', '{}'::jsonb) || jsonb_build_object(%s::text, %s::jsonb), true)
                WHERE id = %s::uuid""",
            (claim_id, json.dumps(finding), run_id),
        )


def code_review_for_claim(pool: ConnectionPool, claim_id: str) -> Optional[dict]:
    """The latest code-review finding for a claim, from whichever run of its project made one, or None."""
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT sr.resources->'code_review'->%s::text
                 FROM claims c
                 JOIN sandbox_runs sr ON (c.project_id IS NOT NULL AND sr.project_id = c.project_id)
                                      OR (c.candidate_project_id IS NOT NULL AND sr.candidate_project_id = c.candidate_project_id)
                WHERE c.id = %s::uuid AND jsonb_exists(sr.resources->'code_review', %s::text)
                ORDER BY sr.created_at DESC LIMIT 1""",
            (claim_id, claim_id, claim_id),
        ).fetchone()
    return row[0] if row and row[0] else None
