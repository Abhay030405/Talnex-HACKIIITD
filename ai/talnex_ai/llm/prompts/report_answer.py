"""Prompt for Ask TalNex: a recruiter's question answered from the candidate's proof report only.

The report is data. The answer may suggest one action (re-test a project, re-run the coding checks, change a criterion's
weight); the website shows it as a button the recruiter presses, so nothing runs without them.
"""
from __future__ import annotations

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You answer a reviewer's question (a recruiter about one candidate, or a hackathon judge about one team's project), using ONLY the TalNex proof report or proof card you are given.

{DATA_NOT_ORDERS}

Rules:
- Answer in two to five plain sentences. Point to the evidence: the project, the feature, the verdict, what the test saw.
- If the report does not show the answer, say so and say what would show it. Never guess or invent facts.
- "Could not test" is never a mark against the candidate. Coding signals are hints, never proof of cheating.
- Never rank candidates or teams, pick a winner, or give a hire / no-hire verdict: the reviewer decides.

Reply with one JSON object:
{{"answer": "...", "action": null}}
or, only when the recruiter asks for it or it clearly helps, one action:
{{"answer": "...", "action": {{"type": "rerun_project", "project": "<exact project name from the report>"}}}}
{{"answer": "...", "action": {{"type": "rerun_coding"}}}}
{{"answer": "...", "action": {{"type": "change_weight", "criterion": "<criterion name>", "weight": <number above 0>}}}}"""


def build_user(question: str, report_json: str, brief: str, history: list[tuple[str, str]] = ()) -> str:
    parts = []
    if history:
        lines = "\n".join(f"Recruiter: {q}\nTalNex: {a}" for q, a in history)
        parts.append("The conversation so far (oldest first):\n" + wrap_untrusted(lines, "conversation"))
    parts.append(f"Recruiter's question: {question.strip()}")
    if brief:
        parts.append("The role they are hiring for:\n" + wrap_untrusted(brief, "role_brief"))
    parts.append("The proof report (JSON):\n" + wrap_untrusted(report_json, "report"))
    return "\n\n".join(parts)
