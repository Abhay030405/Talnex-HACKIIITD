"""Claims for a hackathon project from the organizer's side (fixed-problem events).

The organizer's criteria say what a good project does. The claim reader turns them into things a
visitor can try, and puts each claim in the group named after its criterion, so group scores follow
the organizer's own words. Open-theme events have no criteria: their claims come from the video.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from talnex_ai.claims.reader import Extraction, extract_claims
from talnex_ai.formats import Claim
from talnex_ai.llm.structured import ChatClient


@dataclass(frozen=True)
class Criterion:
    name: str
    description: str
    weight: float


@dataclass(frozen=True)
class ProjectBrief:
    """What the claim stage needs to know about a hackathon project."""

    project_id: str
    team_name: str
    mode: str  # open_theme or fixed_problem
    video_url: Optional[str]
    criteria: tuple[Criterion, ...]


def load_brief(pool: ConnectionPool, project_id: str) -> Optional[ProjectBrief]:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """SELECT p.id::text AS id, p.team_name, p.video_url, e.mode, e.id AS event_id
                 FROM projects p JOIN events e ON e.id = p.event_id WHERE p.id = %s::uuid""",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        criteria = cur.execute(
            """SELECT name, coalesce(description, '') AS description, weight::float8 AS weight
                 FROM criteria WHERE event_id = %s ORDER BY name""",
            (row["event_id"],),
        ).fetchall()
    return ProjectBrief(project_id=row["id"], team_name=row["team_name"], mode=row["mode"],
                        video_url=row["video_url"], criteria=tuple(Criterion(**c) for c in criteria))


def render_criteria(criteria: Sequence[Criterion]) -> str:
    """The criteria as plain text for the claim reader, heaviest first so it sees what matters most."""
    lines = []
    for c in sorted(criteria, key=lambda c: (-c.weight, c.name)):
        line = f"- {c.name} (weight {c.weight:g})"
        lines.append(f"{line}: {c.description}" if c.description else line)
    return "\n".join(lines)


def claims_from_criteria(client: ChatClient, brief: ProjectBrief, *, job_id: Optional[str] = None) -> Extraction:
    """Claims for a fixed-problem project. Open-theme projects have no criteria, so this returns nothing."""
    if brief.mode != "fixed_problem" or not brief.criteria:
        return Extraction(claims=[])
    found = extract_claims(client, render_criteria(brief.criteria), "criteria", project_name=brief.team_name,
                           criteria=[c.name for c in brief.criteria], job_id=job_id)
    return Extraction(claims=[snap_to_criterion(c, brief.criteria) for c in found.claims], findings=found.findings)


def snap_to_criterion(claim: Claim, criteria: Sequence[Criterion]) -> Claim:
    """A group that matches a criterion except for case or spacing gets the criterion's exact name.
    Any other group (a standard one like Core) is kept as written."""
    names = {" ".join(c.name.lower().split()): c.name for c in criteria}
    exact = names.get(" ".join(claim.claim_group.lower().split()))
    return claim.model_copy(update={"claim_group": exact}) if exact else claim
