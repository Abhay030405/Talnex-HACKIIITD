"""Saving and loading claims. A claim belongs to a "subject": a hackathon project, or a project on a resume."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from talnex_ai.claims.reader import same_claim_key
from talnex_ai.formats import Claim

SubjectKind = Literal["project", "candidate_project"]

_COLUMN = {"project": "project_id", "candidate_project": "candidate_project_id"}

_SELECT = """SELECT id::text AS id, text, claim_group, importance, source, track, testable, untestable_reason
               FROM claims"""


@dataclass(frozen=True)
class Subject:
    kind: SubjectKind
    id: str

    @property
    def column(self) -> str:
        # Only ever one of two fixed names, never user input, so it's safe to put into the SQL text.
        return _COLUMN[self.kind]


def _to_claim(row: Mapping[str, Any]) -> Claim:
    return Claim(**row)


def save_claims(pool: ConnectionPool, subject: Subject, claims: Iterable[Claim]) -> list[Claim]:
    """Save claims for a subject and return them with their ids.

    A claim worded like one already saved for the subject isn't saved again (the saved one comes
    back instead), so running the reader twice is safe. All of it happens in one transaction."""
    saved: list[Claim] = []
    with pool.connection() as conn, conn.transaction():
        rows = conn.execute(f"SELECT text, id::text FROM claims WHERE {subject.column} = %s::uuid",
                            (subject.id,)).fetchall()
        existing = {same_claim_key(text): claim_id for text, claim_id in rows}
        for claim in claims:
            key = same_claim_key(claim.text)
            if key not in existing:
                # clock_timestamp(), not the default now(): now() is the same for a whole transaction, which
                # would lose the reader's order between claims of equal importance.
                existing[key] = conn.execute(
                    f"""INSERT INTO claims ({subject.column}, text, claim_group, importance, source, track,
                                            testable, untestable_reason, created_at)
                        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, clock_timestamp()) RETURNING id::text""",
                    (subject.id, claim.text, claim.claim_group, claim.importance, claim.source, claim.track,
                     claim.testable, claim.untestable_reason),
                ).fetchone()[0]
            saved.append(claim.model_copy(update={"id": existing[key]}))
    return saved


def load_claims(pool: ConnectionPool, subject: Subject, *, testable_only: bool = False) -> list[Claim]:
    """A subject's claims, main features first."""
    where = f"WHERE {subject.column} = %s::uuid" + (" AND testable" if testable_only else "")
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(f"{_SELECT} {where} ORDER BY importance DESC, created_at, id", (subject.id,)).fetchall()
    return [_to_claim(r) for r in rows]


def get_claim(pool: ConnectionPool, claim_id: str) -> Optional[Claim]:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(f"{_SELECT} WHERE id = %s::uuid", (claim_id,)).fetchone()
    return _to_claim(row) if row else None
