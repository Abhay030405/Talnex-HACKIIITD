"""Claims for a project on a resume: the resume bullets plus the README of its repository.

Both go through the same claim reader the hackathon side uses; only the source name differs.
"""
from __future__ import annotations

from typing import Optional, Sequence

from talnex_ai.claims.reader import MAX_CLAIMS, Extraction, extract_claims
from talnex_ai.formats import Claim
from talnex_ai.llm.structured import ChatClient

README_MAX_CHARS = 12_000


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
        seen = {" ".join(c.text.lower().split()) for c in claims}
        for claim in more.claims:
            key = " ".join(claim.text.lower().split())
            if key not in seen:
                seen.add(key)
                claims.append(claim)
    return Extraction(claims=claims[:MAX_CLAIMS], findings=findings)
