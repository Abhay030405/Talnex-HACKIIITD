"""The AI opinion (architecture section 16): a UI opinion and an innovation opinion, each part from 1 to 5.

Always shown in its own box labelled LABEL and never part of the TalNex score or any group score.
Two separate model calls with different wording score each opinion. A part's two scores are
averaged, and when they are more than 1 point apart the part says the models disagree. A part
neither call could judge has no score and says why; it is never given a low score instead.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats.parse import parse_model

LABEL = "AI opinion — not tested proof"
DISAGREE_OVER = 1.0
NOT_JUDGED = "could not be judged from what was available"
MAX_REASON = 300

UI_PARTS = {
    "clarity": "Is it obvious what to do?",
    "consistency": "Do the pages shown look like one product (same colours, fonts, buttons)?",
    "feedback": "Are there loading states and clear messages (empty lists, errors, confirmations)?",
    "readability": "Is the text big enough, with good contrast?",
    "phone_width": "Is it usable on a phone screen (the phone-width screenshot)?",
}
INNOVATION_PARTS = {
    "new_vs_existing": "How new is it next to the similar products found by the web search?",
    "new_vs_other_teams": "How different is it from what the other teams of this event built?",
    "technical_difficulty": "How hard is what was actually SEEN working (or read in the code), not what was claimed?",
}

# One part's result from one call: (score 1..5 or None, reason)
Judged = tuple[Optional[int], str]


class _Part(BaseModel):
    model_config = ConfigDict(extra="ignore")
    score: Any = None
    reason: Any = ""


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    parts: dict[str, _Part] = Field(default_factory=dict)


def whole_score(value: Any) -> Optional[int]:
    """A score from 1 to 5, or None for anything else (null, "high", 0, 7, true)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or not 1 <= value <= 5:
        return None
    return int(round(value))


def read_answer(text: str, allowed: Sequence[str]) -> dict[str, Judged]:
    """{part: (score, reason)} from one call's answer. Parts we did not ask about are dropped."""
    answer = parse_model(_Answer, text)
    out: dict[str, Judged] = {}
    for name in allowed:
        part = answer.parts.get(name)
        if part is not None:
            out[name] = (whole_score(part.score), str(part.reason or "").strip()[:MAX_REASON])
    return out


def merge(a: Mapping[str, Judged], b: Mapping[str, Judged], allowed: Sequence[str],
          proof_keys: Optional[Mapping[str, Optional[str]]] = None) -> list[dict]:
    """One entry per part, in the order asked: the average of the scores the two calls gave, both
    scores, whether they disagree, a reason, and the screenshot the part is based on."""
    parts = []
    for name in allowed:
        sa, ra = a.get(name, (None, ""))
        sb, rb = b.get(name, (None, ""))
        given = [(s, r) for s, r in ((sa, ra), (sb, rb)) if s is not None]
        scores = [s for s, _ in given]
        disagree = len(scores) == 2 and abs(scores[0] - scores[1]) > DISAGREE_OVER
        if given:
            reason = next((r for _, r in given if r), NOT_JUDGED)
        else:
            reason = ra or rb or NOT_JUDGED
        part = {"part": name, "score": round(sum(scores) / len(scores), 1) if scores else None,
                "scores": [sa, sb], "disagree": disagree, "reason": reason,
                "proof_key": (proof_keys or {}).get(name)}
        if disagree and ra and rb and ra != rb:
            part["reasons"] = [ra, rb]   # both views, so a judge can see why the models disagree
        parts.append(part)
    return parts
