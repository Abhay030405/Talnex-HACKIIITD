"""Prompt for the claim reader: text in (a README, scoring criteria, resume bullets, video notes), claims out."""
from __future__ import annotations

from typing import Optional, Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

STANDARD_GROUPS = ("Access", "Core", "Logic", "Reliability")

SYSTEM = f"""You read what a software project says about itself and list the claims a reviewer could check by using the project.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"claims": [ ... ]}}. Each claim has exactly these fields:
- "text": one short sentence saying what the project claims it can do, in plain words (for example "Upload an image and get a caption").
- "claim_group": one of {", ".join(STANDARD_GROUPS)}, or the exact name of a scoring criterion when criteria are given and the claim belongs to one.
  Access = signing in and reaching pages. Core = the main features. Logic = whether outputs are correct. Reliability = stays up, handles bad input.
- "importance": 3 for a main feature, 2 for a supporting feature, 1 for a minor detail.
- "source": the source name you are told.
- "testable": true if a person could try it on the live project. false for measurements and results such as "improved speed by 40%", "95% accuracy", "scales to a million users", "reduced costs".
- "untestable_reason": required when testable is false: one short sentence. Leave it out when testable is true.

Rules:
- Only list claims the text actually makes. Never invent features. If the text claims nothing, return {{"claims": []}}.
- One claim per feature; merge duplicates. At most 20 claims, most important first.
- Do not judge quality and do not give scores."""


def build_user(text: str, source: str, *, project_name: Optional[str] = None, criteria: Sequence[str] = ()) -> str:
    parts = []
    if project_name:
        parts.append(f"Project: {project_name}")
    parts.append(f'Source name to use in every claim: "{source}"')
    if criteria:
        parts.append("Scoring criteria (use the exact name as claim_group when a claim belongs to one):\n- "
                     + "\n- ".join(criteria))
    parts.append("Text to read:\n" + wrap_untrusted(text, source))
    return "\n\n".join(parts)
