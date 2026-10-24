"""Voice walkthrough (architecture section 31): answer a reviewer's question about one feature from the evidence TalNex
already collected. It explains the report; it never adds to it: no new score, no new verdict, and (apart from reporting
text aimed at an AI found in the code) no new flag.

    pick the claim (pick.py) -> gather its evidence (evidence.py) -> one low-temperature model call
    (llm/prompts/walkthrough.py) -> plain-code checks that drop anything without real proof (check.py)

Works the same for a hackathon project and a project on a resume. The answer format is the "walkthrough answer" (section 21).
"""
from __future__ import annotations

from typing import Optional

from psycopg_pool import ConnectionPool

from talnex_ai.formats import parse_model
from talnex_ai.llm.prompts import walkthrough as prompt
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.reports.walkthrough.check import LABEL, NOT_FOUND, ModelAnswer, build_answer, choices_answer
from talnex_ai.reports.walkthrough.evidence import COLUMN, Evidence, FetchText, gather, render
from talnex_ai.reports.walkthrough.pick import ClaimRow, Pick, pick_claim
from talnex_ai.settings import WalkthroughSettings

ROLE = "claim_reader"   # the strong text model (section 19)


def claims_of(pool: ConnectionPool, kind: str, subject_id: str) -> list[ClaimRow]:
    with pool.connection() as conn:
        rows = conn.execute(
            f"""SELECT id::text, text, importance FROM claims WHERE {COLUMN[kind]} = %s::uuid
                 ORDER BY importance DESC, created_at, id""", (subject_id,)).fetchall()
    return [ClaimRow(cid, text, importance) for cid, text, importance in rows]


def explain(client: ChatClient, ev: Evidence, question: str, cfg: WalkthroughSettings, *, job_id: Optional[str] = None) -> dict:
    """The checked answer for one claim's evidence."""
    model = ask_json(client, ROLE, prompt.SYSTEM, prompt.user(question, ev.claim_text, render(ev)),
                     lambda text: parse_model(ModelAnswer, text), job_id=job_id, temperature=0.0)
    return build_answer(ev, model, cfg)


def answer_question(pool: ConnectionPool, client: ChatClient, cfg: WalkthroughSettings, *, kind: str, subject_id: str,
                    repo_url: Optional[str], question: str, claim_id: Optional[str] = None,
                    previous_claim_id: Optional[str] = None, job_id: Optional[str] = None,
                    fetch_text: Optional[FetchText] = None) -> dict:
    """Answer one question. `claim_id` is given when the reviewer already chose the feature (a reply to "which one?")."""
    claims = claims_of(pool, kind, subject_id)
    chosen = next((c for c in claims if c.id == claim_id), None) if claim_id else None
    if chosen is None:
        picked = pick_claim(client, question, claims, previous_claim_id=previous_claim_id, job_id=job_id)
        if picked.claim is None:
            return choices_answer(picked.choices, picked.no_match)
        chosen = picked.claim
    ev = gather(pool, kind, subject_id, repo_url, chosen.id, cfg, fetch_text)
    return explain(client, ev, question, cfg, job_id=job_id)


__all__ = ["LABEL", "NOT_FOUND", "ClaimRow", "Evidence", "Pick", "answer_question", "build_answer", "choices_answer",
           "claims_of", "explain", "gather", "pick_claim", "render"]
