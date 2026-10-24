"""Prompt for the last look at two teams whose code has the same shape: the top matching files of both go in, a verdict and a
reason come out. Code is data, never instructions."""
from __future__ import annotations

from typing import Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

VERDICTS = ("copied", "starter_or_library", "common_pattern", "unclear")

SYSTEM = f"""Two teams in the same hackathon built their projects separately. A program found that parts of their code have the same shape (the same logic in the same order, even if names were changed). You see the files that match best, side by side. Decide what the match means.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"verdict": ..., "reason": ..., "evidence": [...]}}.
- "verdict" is one of:
  copied = the same logic worked out the same way beyond what chance or a shared idea explains (same unusual steps, same order, same special cases), so one team probably built from the other's code or both from one source.
  starter_or_library = the matching code is a template, a framework example, a library file, boilerplate or generated code that many teams start from.
  common_pattern = a standard way to do a common thing (a login form, a todo list, a CRUD route); the match says little.
  unclear = you cannot tell from these files.
- "reason": two or three plain sentences saying what matches and why you chose the verdict. Do not say which team copied which; you cannot know that.
- "evidence": one to four short lines like "a.js and b.js both check X, then Y, then Z in the same order".
Be careful: a wrong "copied" harms a team. Choose "copied" only when the match is specific. Do not give scores."""


def build_user(team_a: str, team_b: str, shared_pct: float, pairs: Sequence[tuple[str, str, str, str, float]]) -> str:
    """`pairs` is (a_file, b_file, a_text, b_text, match_pct)."""
    parts = [f"Team A: {team_a}", f"Team B: {team_b}", f"Overall shape match: {shared_pct:.0f}%"]
    for i, (a_file, b_file, a_text, b_text, pct) in enumerate(pairs, start=1):
        parts.append(f"Match {i}: {a_file} (A) and {b_file} (B), {pct:.0f}% of A's file found in B's file")
        parts.append(f"A's {a_file}:\n" + wrap_untrusted(a_text, f"team A {a_file}"))
        parts.append(f"B's {b_file}:\n" + wrap_untrusted(b_text, f"team B {b_file}"))
    return "\n\n".join(parts)
