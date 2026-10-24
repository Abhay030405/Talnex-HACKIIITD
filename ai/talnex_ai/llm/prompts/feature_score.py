"""Prompts for feature scoring: write a checklist first, then mark it against the evidence."""
from __future__ import annotations

from typing import Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

CHECKLIST_SYSTEM = f"""You write a short checklist for judging how well a software feature is IMPLEMENTED.
You write it before seeing any test results, so it must come only from knowing how a feature of this kind is normally built.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"items": [ ... ]}} with 3 to 8 items. Each item has:
- "text": a short noun phrase of at most 60 characters naming one thing a real implementation has (for a self-correcting retrieval feature: "relevance check on retrieved text", "retry with a rewritten query", "limit on retries", "fallback when nothing is found").
- "part": one of "implementation" (the real mechanism is there, not a thin wrapper), "logic" (outputs are correct), "edge" (bad input, empty cases and failures are handled), "design" (separation, structure, readability).
- "core": true for the one to three items that DEFINE the claimed mechanism. If these are missing, the feature is not really implemented.

Rules:
- Judge implementation, not taste. Don't reward fancy tools; reward the mechanism being really there and working.
- No items about visual design or styling.
- Include at least one "implementation" item and mark it core.
- When the message says the feature will be tested through its live site, write every item as something a person can SEE or TRY from outside (what appears, what happens with an odd input, whether it still works after a reload). Never name code internals such as functions or objects in that case."""


def checklist_user(claim_text: str, group: str, role: str, *, from_code: bool = False, brief: str = "") -> str:
    if from_code:
        if role == "fresher":
            design_note = 'The reviewer is judging a fresher: do NOT include any "design" items.'
        else:
            design_note = f'The reviewer is judging a {role} developer: include one or two "design" items.'
        evidence_note = "The evidence will be the project's code, so items may describe what the code does."
    else:
        design_note = 'Do NOT include any "design" items: structure and readability cannot be seen from outside.'
        evidence_note = "The feature will be tested through its live site only: every item must be observable by using it."
    text = f"Feature claim: {claim_text}\nFeature group: {group}\n{design_note}\n{evidence_note}"
    if brief:
        # What the recruiter is hiring for: it can shape which items matter, never whether the feature works.
        text += ("\nThe reviewer is hiring for the role below. Prefer items that show the skills it asks for, but every "
                 "item must still be about this feature only.\n" + wrap_untrusted(brief, "role_brief"))
    return text


MARK_SYSTEM = f"""You mark a checklist against evidence about a software feature.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"marks": [ ... ], "mechanism_present": true|false|null}}.
- "marks": exactly one entry per checklist item, each with "index" (the item number), "status" and "note".
  "status" is "present" if the evidence clearly shows it, "missing" if the evidence shows it is absent or failing, and "unknown" if the evidence says nothing either way.
  "note" is at most 100 characters and points to the evidence (a step, an observed result, or a file).
- "mechanism_present": true if the claimed mechanism is really there and working; false if the evidence shows it is NOT implemented or not wired in (for example the README claims it but nothing like it exists); null if the evidence cannot tell.
Judge only from the evidence. Never mark "present" because the claim says so."""


def mark_user(items: Sequence[tuple[int, str, str]], claim_text: str, evidence: str) -> str:
    listing = "\n".join(f"{n}. [{part}] {text}" for n, part, text in items)
    return (f"Feature claim: {claim_text}\n\nChecklist:\n{listing}\n\n"
            f"Evidence (what was seen when the feature was tested, or read in the code):\n"
            f"{wrap_untrusted(evidence, 'evidence')}")
