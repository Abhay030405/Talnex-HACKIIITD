"""The claim reader: turns text into claims.

It works the same for a README, scoring criteria, resume bullets or video notes; only the source
name changes. Shared parts never ask which mode (recruiter or hackathon) they're in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from talnex_ai.formats import Claim, ClaimSource, parse_list
from talnex_ai.llm.prompts.claim_reader import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.safety.hidden_instructions import Finding, find_hidden_instructions

MAX_CLAIMS = 20

# Results and measurements can't be tried by a visitor. The model is told this too; this is the
# safety net for when it forgets. It can only switch "testable" off, never on.
_MEASUREMENT = re.compile(
    r"\b\d+(?:\.\d+)?\s?x\s+(?:faster|slower|cheaper|better|more)\b|"
    r"\b\d+(?:\.\d+)?\s?%\s*(?:accuracy|precision|recall|uptime|success|faster|slower|cheaper|improvement|reduction|less|more)\b|"
    r"\b(?:reduced|improved|increased|decreased|cut|boosted|lowered|saved)\b.{0,40}\bby\b.{0,12}\d|"
    r"\bscal(?:es|able|ability)\b.{0,30}\b\d[\d,]*\+?\s?(?:k|m)?\s?(?:users|requests|rps|qps)\b|"
    r"\b(?:accuracy|precision|recall|f1|latency|throughput)\b.{0,20}\b\d",
    re.IGNORECASE,
)
MEASUREMENT_REASON = "a measurement or result, not something a visitor can try"


@dataclass
class Extraction:
    claims: list[Claim]
    # Text aimed at an AI checker found in the source. It becomes a "hidden AI instructions" flag.
    findings: list[Finding] = field(default_factory=list)


def enforce_measurement_rule(claim: Claim) -> Claim:
    if claim.testable and _MEASUREMENT.search(claim.text):
        return claim.model_copy(update={"testable": False, "untestable_reason": MEASUREMENT_REASON})
    return claim


def same_claim_key(text: str) -> str:
    """Two wordings count as the same claim when they differ only in case, spacing or end punctuation."""
    return " ".join(text.lower().split()).rstrip(".!")


def extract_claims(
    client: ChatClient,
    text: str,
    source: ClaimSource,
    *,
    project_name: Optional[str] = None,
    criteria: Sequence[str] = (),
    job_id: Optional[str] = None,
) -> Extraction:
    """Read `text` and return the claims it makes, plus any hidden instructions found in it."""
    findings = find_hidden_instructions(text)
    if not text.strip():
        return Extraction(claims=[], findings=findings)

    claims = ask_json(
        client, "claim_reader", SYSTEM, build_user(text, source, project_name=project_name, criteria=criteria),
        lambda answer: parse_list(Claim, answer, key="claims"), job_id=job_id,
    )

    unique: list[Claim] = []
    seen: set[str] = set()
    for claim in claims:
        # We know the source; never trust the model's copy of it, or an id it made up.
        claim = enforce_measurement_rule(claim.model_copy(update={"source": source, "id": None}))
        key = same_claim_key(claim.text)
        if key not in seen:
            seen.add(key)
            unique.append(claim)
    # If there are too many, keep the main features: a stable sort keeps the reader's order within each level.
    unique.sort(key=lambda c: -c.importance)
    return Extraction(claims=unique[:MAX_CLAIMS], findings=findings)
