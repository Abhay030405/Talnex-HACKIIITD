"""Claims for a project on a resume: the resume bullets plus the README of its repository.

Both go through the same claim reader the hackathon side uses; only the source name differs.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

from talnex_ai.claims.reader import MAX_CLAIMS, Extraction, extract_claims
from talnex_ai.formats import Claim
from talnex_ai.llm.structured import ChatClient
from talnex_ai.testing.scope import _STOP, _stem

README_MAX_CHARS = 12_000
SAME_CLAIM_SHARE = 0.6   # a README claim sharing this much of its meaning words with a bullet repeats it


def _meaning(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


def repeats(text: str, other: str) -> bool:
    """Do two claims say the same thing in other words? "Upload a photo and the app writes a caption" and "Upload a
    photo and CaptionIt writes a caption" do; "Add a todo" and "Delete a todo" don't."""
    a, b = _meaning(text), _meaning(other)
    return bool(a and b) and len(a & b) / len(a | b) >= SAME_CLAIM_SHARE


def claims_from_resume(client: ChatClient, name: str, bullets: Sequence[str], readme: Optional[str],
                       *, job_id: Optional[str] = None) -> Extraction:
    """Bullets first (source `resume`), then the README (source `readme`); a README claim that repeats a bullet is dropped."""
    bullet_text = "\n".join(f"- {b}" for b in bullets)
    out = extract_claims(client, bullet_text, "resume", project_name=name, job_id=job_id)
    claims: list[Claim] = list(out.claims)
    findings = list(out.findings)

    if readme and readme.strip():
        more = extract_claims(client, readme[:README_MAX_CHARS], "readme", project_name=name, job_id=job_id)
        findings += more.findings
        for claim in more.claims:
            if not any(repeats(claim.text, c.text) for c in claims):
                claims.append(claim)
    return Extraction(claims=claims[:MAX_CLAIMS], findings=findings)
