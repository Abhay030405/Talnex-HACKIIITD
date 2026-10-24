"""The independent proof checker: a second look at the screenshots, from a fresh call that sees
only the pictures and the expected result, never the test run's verdict."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import FormatError, parse_model
from talnex_ai.llm.prompts.proof_checker import SYSTEM, user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.testing.scope import unchanged_value

log = logging.getLogger("talnex.proof")

MAX_IMAGES = 8  # plans have 2 to 5 steps (10 at most), plus the final check

Outcome = Literal["works", "partly_works", "broken", "blocked"]

# A "works" answer whose own description says the feature is missing or failing contradicts itself.
_SAYS_FAILED = re.compile(
    r"\b(?:not (?:visible|shown|present|there|found|working|displayed)|missing|no such|nowhere|"
    r"(?:does|did) not (?:appear|show|exist|work|happen|load|change)|didn't (?:appear|show|work|happen)|"
    r"fail(?:s|ed)?|still (?:shows? )?(?:0|zero|empty))\b",
    re.IGNORECASE,
)


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    outcome: Outcome
    seen: str = Field(min_length=1, max_length=500)
    screenshot_clear: bool = True


class FileReader(Protocol):
    def get_bytes(self, key: str) -> bytes: ...


@dataclass(frozen=True)
class ProofCheck:
    outcome: Outcome
    seen: str
    screenshot_clear: bool
    images_used: int


def _parse(text: str, claim_text: str = "") -> _Answer:
    answer = parse_model(_Answer, text)
    contradiction = _SAYS_FAILED.search(answer.seen)
    if answer.outcome == "works" and contradiction:
        raise FormatError(f'the outcome is works, but "seen" says "{contradiction.group(0)}". '
                          "Make the outcome agree with what the pictures show.")
    start = unchanged_value(claim_text, answer.seen) if answer.outcome == "works" else None
    if start:
        raise FormatError(f'the outcome is works, but the value you describe ("{start}") is still at its starting point. '
                          "Answer partly_works or broken, unless the pictures show it changing: then say how it changed.")
    return answer


def screens_for_check(steps: Sequence, max_images: int = MAX_IMAGES) -> list[str]:
    """One screenshot per plan step (its last action), then the final state, oldest first.

    A step can take several actions; only the last one shows the step's result. Picking by step means a
    claim with several parts (convert to EUR, then GBP, then INR) is judged on every part, not only on
    the last few actions. With more steps than room, the latest steps are kept."""
    groups: list[list] = []  # runs of actions that belong to the same plan step (same expected result)
    for step in steps:
        if groups and getattr(groups[-1][-1], "expected", None) == getattr(step, "expected", None):
            groups[-1].append(step)
        else:
            groups.append([step])
    picked: list[str] = []
    for group in groups:  # the last action of each step that has a screenshot
        key = next((s.proof_key for s in reversed(group) if getattr(s, "proof_key", None)), None)
        if key and key not in picked:
            picked.append(key)
    return picked[-max_images:]


def check_proof(
    client: ChatClient,
    files: FileReader,
    *,
    claim_text: str,
    expected_result: str,
    proof_keys: Sequence[Optional[str]],
    job_id: Optional[str] = None,
    max_images: int = MAX_IMAGES,
) -> ProofCheck:
    """Look at the last few screenshots of a run and say whether the expected result is visible.

    With no screenshots to look at, the answer is "blocked" (we can't confirm), never a verdict."""
    pictures: list[bytes] = []
    for key in [k for k in proof_keys if k][-max_images:]:
        try:
            pictures.append(files.get_bytes(key))
        except Exception as err:
            log.warning("could not read screenshot %s: %s", key, err)
    if not pictures:
        return ProofCheck("blocked", "there were no screenshots to look at", False, 0)

    answer = ask_json(client, "proof_checker", SYSTEM, user(claim_text, expected_result, len(pictures)), lambda text: _parse(text, claim_text),
                      job_id=job_id, images=pictures, temperature=0.0)
    return ProofCheck(answer.outcome, answer.seen, answer.screenshot_clear, len(pictures))
