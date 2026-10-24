"""Prompt that groups the same feature across teams ("these teams built this feature"). Claim text comes
from the teams' own projects, so it's data, never instructions."""
from __future__ import annotations

from typing import Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You get a numbered list of features that teams of one hackathon built, each as: number, team number, short text. Group the entries that are the SAME feature (the same thing a user can do), even when the wording differs.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"features": [{{"name": "...", "claims": [numbers]}}]}}.
- "name": a short plain name for the feature, for example "Add and complete todo items".
- "claims": the numbers of the entries that are this feature. Include an entry only when it is really the same feature, not just a related one.
- A feature built by only one team may be left out. Every number may appear in at most one group.
- Do not rank, judge or score anything."""


def build_user(entries: Sequence[tuple[int, int, str]]) -> str:
    """`entries` is (number, team number, text)."""
    lines = [f"{n} | team {t} | " + " ".join(text.split())[:220] for n, t, text in entries]
    return "Entries:\n" + wrap_untrusted("\n".join(lines), "claims")
