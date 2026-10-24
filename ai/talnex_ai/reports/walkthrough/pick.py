"""Pick the feature (claim) a question is about (architecture section 31.3, step 3).

A cheap word match first. The model is asked only when the words do not point at exactly one claim. When the question
matches no claim or several, the answer lists the claims and asks which one is meant: TalNex never guesses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import parse_model
from talnex_ai.llm.prompts import walkthrough as prompt
from talnex_ai.llm.structured import ChatClient, ask_json

ROLE = "claim_reader"

# Words that say how to answer, not which feature: they never decide the match.
_IGNORE = {
    "a", "an", "and", "are", "as", "at", "be", "built", "by", "can", "did", "do", "does", "explain", "feature", "features",
    "for", "from", "how", "i", "in", "is", "it", "its", "me", "my", "of", "on", "or", "part", "please", "show", "tell", "that",
    "the", "their", "them", "they", "this", "through", "to", "us", "walk", "was", "what", "when", "where", "which", "who",
    "why", "with", "work", "works", "you", "your", "about", "app", "project", "code",
}


@dataclass(frozen=True)
class ClaimRow:
    id: str
    text: str
    importance: int = 2


@dataclass
class Pick:
    claim: Optional[ClaimRow] = None
    choices: list[ClaimRow] = field(default_factory=list)
    no_match: bool = False      # the question matched none of the claims


class _ModelPick(BaseModel):
    model_config = ConfigDict(extra="ignore")
    claim_ids: list[str] = Field(default_factory=list)


def _words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in _IGNORE or len(w) < 2:
            continue
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return out


def match_by_words(question: str, claims: Sequence[ClaimRow]) -> Optional[ClaimRow]:
    """The one claim that shares clearly more words with the question than any other, or None."""
    asked = _words(question)
    if not asked:
        return None
    scored = sorted(((len(asked & _words(c.text)), c) for c in claims), key=lambda pair: -pair[0])
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def pick_claim(client: ChatClient, question: str, claims: Sequence[ClaimRow], *, previous_claim_id: Optional[str] = None,
               job_id: Optional[str] = None) -> Pick:
    if not claims:
        return Pick(no_match=True)
    found = match_by_words(question, claims)
    if found is not None:
        return Pick(claim=found)

    by_id = {c.id: c for c in claims}
    previous = previous_claim_id if previous_claim_id in by_id else None
    answer = ask_json(client, ROLE, prompt.PICK_SYSTEM,
                      prompt.pick_user(question, [(c.id, c.text, c.importance) for c in claims], previous),
                      lambda text: parse_model(_ModelPick, text), job_id=job_id, temperature=0.0)
    named = list(dict.fromkeys(i for i in answer.claim_ids if i in by_id))   # never an id the project does not have
    if len(named) == 1:
        return Pick(claim=by_id[named[0]])
    if named:
        return Pick(choices=[by_id[i] for i in named])
    return Pick(choices=list(claims), no_match=True)
