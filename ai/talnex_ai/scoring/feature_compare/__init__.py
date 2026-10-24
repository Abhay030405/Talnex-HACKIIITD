"""Feature comparison (architecture section 15): "these teams built this feature best". Always the top
3, never one best team.

The model only GROUPS claims that are the same feature across teams. Everything that orders teams is
plain code, so the same results always give the same order: verdict (works, then partly works, then
reviewed from code) -> feature score -> fewer steps -> claim id (a stable last tie-break, never a
quality judgement). A team whose coverage is low isn't compared, and a feature fewer than two teams
built isn't listed. "Could not test" and "broken" claims are simply not part of the comparison, so
they never make a team look better or worse here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import parse_model
from talnex_ai.llm.prompts.feature_group import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json

TOP = 3
MIN_COVERAGE = 50.0  # a team with less coverage than this (percent) isn't compared
VERDICT_RANK = {"works": 3, "partly_works": 2, "reviewed_from_code": 1}
STANDARD_GROUPS = ("Access", "Core", "Logic", "Reliability")
MAX_ENTRIES_PER_CALL = 150


@dataclass
class Entry:
    claim_id: str
    project_id: str
    team_name: str
    group: str
    text: str
    verdict: str
    confidence: str
    feature_score: Optional[float]
    steps: int
    reason: str = ""
    proof_keys: list[str] = field(default_factory=list)


class _Group(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    claims: list[int] = Field(default_factory=list, max_length=60)


class _Grouping(BaseModel):
    model_config = ConfigDict(extra="ignore")
    features: list[_Group] = Field(default_factory=list, max_length=80)


def order_key(e: Entry) -> tuple:
    """Best first: a better verdict, then a higher feature score, then fewer steps, then the claim id."""
    score = e.feature_score if e.feature_score is not None else -1.0
    return (-VERDICT_RANK.get(e.verdict, 0), -score, e.steps, e.claim_id)


def eligible(entries: Sequence[Entry], coverage: dict[str, float]) -> list[Entry]:
    return [e for e in entries if e.verdict in VERDICT_RANK and coverage.get(e.project_id, 0.0) >= MIN_COVERAGE]


def _feature_key(name: str) -> str:
    return " ".join(name.lower().split())


def group_by_meaning(model: ChatClient, entries: Sequence[Entry], *,
                     job_id: Optional[str] = None) -> list[tuple[str, list[Entry]]]:
    """Ask the model which entries are the same feature. Only valid answers are used: a number that
    doesn't exist is ignored, an entry is in one group at most, a team has one entry per group (its
    best), and a group needs at least two teams. Large events are asked in chunks; groups with the same
    name from different chunks are joined, so one feature isn't split in two."""
    teams = {p: i for i, p in enumerate(sorted({e.project_id for e in entries}), start=1)}
    joined: dict[str, tuple[str, list[Entry]]] = {}
    for start in range(0, len(entries), MAX_ENTRIES_PER_CALL):
        numbered = dict(enumerate(entries[start:start + MAX_ENTRIES_PER_CALL], start=1))
        answer = ask_json(model, "claim_reader", SYSTEM,
                          build_user([(n, teams[e.project_id], e.text) for n, e in numbered.items()]),
                          lambda text: parse_model(_Grouping, text), job_id=job_id, max_tokens=4000, temperature=0.0)
        used: set[int] = set()
        for group in answer.features:
            numbers = [n for n in dict.fromkeys(group.claims) if n in numbered and n not in used]
            used.update(numbers)
            name, members = joined.setdefault(_feature_key(group.name), (group.name, []))
            members.extend(numbered[n] for n in numbers)

    found = []
    for name, members in joined.values():
        best: dict[str, Entry] = {}
        for e in members:
            if e.project_id not in best or order_key(e) < order_key(best[e.project_id]):
                best[e.project_id] = e
        if len(best) >= 2:
            found.append((name, sorted(best.values(), key=order_key)))
    return found


def best_teams(members: Sequence[Entry]) -> list[dict]:
    return [{"project_id": e.project_id, "team_name": e.team_name, "claim_id": e.claim_id, "claim_text": e.text,
             "verdict": e.verdict, "confidence": e.confidence, "feature_score": e.feature_score, "steps": e.steps,
             "reason": e.reason, "proof_keys": e.proof_keys[:2],
             "label": "reviewed from code, not run" if e.verdict == "reviewed_from_code" else None}
            for e in sorted(members, key=order_key)[:TOP]]


def best_by_group(scores: dict[str, dict[str, tuple[Optional[float], float]]],
                  names: dict[str, str]) -> list[tuple[str, list[dict]]]:
    """Open-theme extra: the teams with the best Access, Core, Logic and Reliability.
    `scores` is {group: {project_id: (score, coverage)}}. Only teams with a score and enough coverage
    are listed; a group fewer than two teams were scored in is left out."""
    found = []
    for group in STANDARD_GROUPS:
        rows = [(pid, s, c) for pid, (s, c) in scores.get(group, {}).items() if s is not None and c >= MIN_COVERAGE]
        rows.sort(key=lambda r: (-r[1], names.get(r[0], ""), r[0]))
        if len(rows) >= 2:
            found.append((f"Best {group}", [{"project_id": p, "team_name": names.get(p, ""), "group": group,
                                             "score": s, "coverage": c} for p, s, c in rows[:TOP]]))
    return found
