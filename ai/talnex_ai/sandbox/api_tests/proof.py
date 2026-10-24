"""The independent check of a backend test: a fresh model call that sees only the saved request and answer records and the
expected result, never the test's own conclusion (architecture 28.10)."""
from __future__ import annotations

import json
import logging
from typing import Optional, Protocol, Sequence

from talnex_ai.formats import parse_model
from talnex_ai.llm.prompts.http_proof_checker import SYSTEM, user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.testing.proof_check import ProofCheck, _Answer

log = logging.getLogger("talnex.api_proof")

MAX_RECORDS = 8
MAX_CHARS = 9000


class FileReader(Protocol):
    def get_bytes(self, key: str) -> bytes: ...


def transcript(records: Sequence[dict]) -> str:
    """The records as plain text for the checker. Only what happened: the request, the answer, and what was expected."""
    parts = []
    for i, rec in enumerate(records, start=1):
        req = rec.get("request", {})
        lines = [f"[{i}] {req.get('method', '?')} {req.get('path', '?')}"]
        if req.get("body"):
            lines.append(f"    sent: {req['body'][:600]}")
        if rec.get("parallel", 1) > 1:
            lines.append(f"    ({rec['parallel']} identical requests were sent at the same time; the first answers are shown)")
        for r in rec.get("responses", [])[:2]:
            if r.get("status"):
                lines.append(f"    answer: status {r['status']} in {r.get('duration_ms', '?')} ms: {str(r.get('body', ''))[:700]}")
            else:
                lines.append(f"    no answer: {r.get('error') or 'unknown'}")
        lines.append(f"    this step should give: {rec.get('expected', '?')}")
        parts.append("\n".join(lines))
    return "\n".join(parts)[:MAX_CHARS]


def check_http_proof(
    client: ChatClient,
    files: FileReader,
    *,
    claim_text: str,
    expected_result: str,
    proof_keys: Sequence[Optional[str]],
    job_id: Optional[str] = None,
) -> ProofCheck:
    """With no records to read the answer is "blocked" (we cannot confirm), never a verdict."""
    records: list[dict] = []
    for key in [k for k in proof_keys if k][-MAX_RECORDS:]:
        try:
            records.append(json.loads(files.get_bytes(key)))
        except Exception as exc:
            log.warning("could not read proof record %s: %s", key, exc)
    if not records:
        return ProofCheck("blocked", "there were no records to look at", False, 0)
    answer = ask_json(client, "proof_checker", SYSTEM, user(claim_text, expected_result, transcript(records)),
                      lambda text: parse_model(_Answer, text), job_id=job_id)
    return ProofCheck(answer.outcome, answer.seen, answer.screenshot_clear, len(records))
