"""Compare every pair of teams by the shape of their code (architecture section 12, "Copying between teams").

Input is the fingerprint of each team's repo (`fingerprint.py`). Starter code is removed first: a run of code that many teams in the
event share is a template or a library everybody started from, not a sign that two teams copied each other. What is left is compared
pair by pair. "Shared" is measured against the SMALLER of the two teams' own code, so a small copy of a big project still shows.
A team with too little code of its own is not compared at all (never a result, never a mark against it).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

MIN_OWN_HASHES = 30        # a team with less own code than this is left out of the comparison
MIN_FILE_HASHES = 8        # a file with less than this is too small to point at
FILE_MATCH_PCT = 50.0      # a file counts as matching when this much of it is found in one file of the other team


@dataclass
class Team:
    id: str
    name: str
    files: Mapping[str, Sequence[int]]        # path -> hashes (from the fingerprint)


@dataclass
class Pair:
    a_id: str
    b_id: str
    shared_pct: float
    shared: int
    a_size: int
    b_size: int
    matching_files: list[dict] = field(default_factory=list)   # [{a_file, b_file, pct, shared}]


@dataclass
class Comparison:
    pairs: list[Pair]
    starter_removed: int                      # how many distinct hashes were treated as starter code
    starter_threshold: Optional[int]          # a hash in this many teams is starter code (None: too few teams to tell)
    left_out: list[str]                       # team ids with too little own code


def starter_threshold(team_count: int, share: float = 0.5) -> Optional[int]:
    """Starter code can only be told apart from copying when several teams share it. With fewer than 3 teams it cannot."""
    if team_count < 3:
        return None
    return max(3, math.ceil(team_count * share))


def compare(teams: Sequence[Team], *, share: float = 0.5) -> Comparison:
    threshold = starter_threshold(len(teams), share)
    seen_in: dict[int, int] = {}
    per_team: dict[str, set[int]] = {}
    for t in teams:
        hs = {h for hashes in t.files.values() for h in hashes}
        per_team[t.id] = hs
        for h in hs:
            seen_in[h] = seen_in.get(h, 0) + 1
    starter = {h for h, n in seen_in.items() if threshold is not None and n >= threshold}

    own = {t.id: per_team[t.id] - starter for t in teams}
    usable = [t for t in teams if len(own[t.id]) >= MIN_OWN_HASHES]
    left_out = [t.id for t in teams if len(own[t.id]) < MIN_OWN_HASHES]

    pairs: list[Pair] = []
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            common = own[a.id] & own[b.id]
            if not common:
                pairs.append(Pair(a.id, b.id, 0.0, 0, len(own[a.id]), len(own[b.id])))
                continue
            pct = 100.0 * len(common) / min(len(own[a.id]), len(own[b.id]))
            pairs.append(Pair(a.id, b.id, round(pct, 2), len(common), len(own[a.id]), len(own[b.id]),
                              _matching_files(a, b, starter)))
    return Comparison(pairs, len(starter), threshold, left_out)


def _matching_files(a: Team, b: Team, starter: set[int]) -> list[dict]:
    b_sets = {p: {h for h in hs if h not in starter} for p, hs in b.files.items()}
    out: list[dict] = []
    for path, hashes in a.files.items():
        mine = {h for h in hashes if h not in starter}
        if len(mine) < MIN_FILE_HASHES:
            continue
        best_path, best = None, 0
        for other, theirs in b_sets.items():
            n = len(mine & theirs)
            if n > best:
                best_path, best = other, n
        pct = 100.0 * best / len(mine)
        if best_path and pct >= FILE_MATCH_PCT and best >= MIN_FILE_HASHES:
            out.append({"a_file": path, "b_file": best_path, "pct": round(pct, 1), "shared": best})
    out.sort(key=lambda m: (-m["shared"], m["a_file"]))
    return out[:8]


def level_for(pct: float, review_pct: float, strong_pct: float) -> Optional[str]:
    """Review at the lower line, strong at the higher; below it no flag (the pair is still saved)."""
    if pct >= strong_pct:
        return "strong"
    if pct >= review_pct:
        return "review"
    return None
