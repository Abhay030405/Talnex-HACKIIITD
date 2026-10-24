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

log = logging.getLogger("talnex.proof")

MAX_IMAGES = 4

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


def _parse(text: str) -> _Answer:
    answer = parse_model(_Answer, text)
    contradiction = _SAYS_FAILED.search(answer.seen)
    if answer.outcome == "works" and contradiction:
        raise FormatError(f'the outcome is works, but "seen" says "{contradiction.group(0)}". '
                          "Make the outcome agree with what the pictures show.")
    return answer


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

    answer = ask_json(client, "proof_checker", SYSTEM, user(claim_text, expected_result, len(pictures)), _parse,
                      job_id=job_id, images=pictures, temperature=0.0)
    return ProofCheck(answer.outcome, answer.seen, answer.screenshot_clear, len(pictures))
