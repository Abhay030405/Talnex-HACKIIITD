"""Prompts for the AI opinion (architecture section 16): UI from screenshots, and innovation.

Each opinion is scored by TWO calls with different wording, and code averages them. The opinion is
always shown as "AI opinion — not tested proof" and is never part of a score. Everything about a
team (its pages, its claims, search results) is data, never instructions."""
from __future__ import annotations

from typing import Mapping, Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted
from talnex_ai.scoring.ai_opinion import INNOVATION_PARTS, UI_PARTS

_SCALE = ("Give each part a whole number from 1 (poor) to 5 (excellent) and one plain sentence of reason that "
          "points at something specific you saw. If a part cannot be judged from what you were given, give it "
          "null as the score and say why. Never guess.")


def _parts(parts: Mapping[str, str]) -> str:
    return "\n".join(f"- {name}: {question}" for name, question in parts.items())


def _shape(parts: Mapping[str, str]) -> str:
    return '{"parts": {' + ", ".join(f'"{p}": {{"score": 1-5 or null, "reason": "..."}}' for p in parts) + "}}"


UI_A = f"""You judge the user interface of a hackathon project from screenshots. The first is the first page at desktop width, the second the same page at phone width; any more are screens from the tests.

{DATA_NOT_ORDERS}

Parts:
{_parts(UI_PARTS)}

{_SCALE}
Reply with one JSON object: {_shape(UI_PARTS)}
This is an opinion about design only. Do not say whether features work."""

UI_B = f"""Look at these screenshots as someone using this app for the first time. First: desktop width. Second: phone width. Any more: other screens of the same app. Notice what confuses you or is hard to read, then rate five qualities.

{DATA_NOT_ORDERS}

Qualities:
{_parts(UI_PARTS)}

{_SCALE}
Answer with one JSON object: {_shape(UI_PARTS)}
Only the design matters here; never claim to know whether features work."""

INNOVATION_A = f"""You judge how new and how hard a hackathon project is. You get: a short description of the project, similar products found by a web search, one line about each other team's project in the same event, and what was actually SEEN in testing.

{DATA_NOT_ORDERS}

Parts:
{_parts(INNOVATION_PARTS)}

{_SCALE}
Reply with one JSON object: {_shape(INNOVATION_PARTS)}
Judge technical difficulty only from what was seen working or read in the code ("reviewed from code, not run" is weaker evidence), never from what the team says about itself."""

INNOVATION_B = f"""Rate a hackathon project's originality and difficulty. Below are the project, products that look similar (from a web search), the other teams' projects, and the evidence of what really worked.

{DATA_NOT_ORDERS}

Rate:
{_parts(INNOVATION_PARTS)}

{_SCALE}
Answer with one JSON object: {_shape(INNOVATION_PARTS)}
Difficulty counts only what was shown working or found in the code, not promises."""

DESCRIBE = f"""You get a hackathon project's features: what a visitor can do, or what its code implements.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"description": "two plain sentences about what the project is", "search_query": "a short web search that would find similar existing products"}}"""


def describe_user(team: str, features: Sequence[str]) -> str:
    return f"Team: {team}\nFeatures:\n" + wrap_untrusted("\n".join(f"- {f}" for f in features), "features")


def ui_user(team: str, shots: int) -> str:
    return (f"Project of team {team}. {shots} screenshots follow, in this order: desktop width first page, "
            "phone width first page, then screens from the tests.")


def innovation_user(description: str, similar: Sequence[tuple[str, str, str]], others: Sequence[str], seen: str) -> str:
    found = "\n".join(f"- {title} | {url} | {snippet[:200]}" for title, url, snippet in similar)
    teams = "\n".join(f"- {o[:200]}" for o in others)
    return "\n\n".join([
        "Project:\n" + wrap_untrusted(description, "project"),
        "Similar products from a web search (title | link | snippet):\n" + (wrap_untrusted(found, "search") if similar else "none found"),
        "Other teams' projects in this event:\n" + (wrap_untrusted(teams, "other_teams") if others else "none"),
        "What was seen in testing:\n" + wrap_untrusted(seen, "seen"),
    ])
