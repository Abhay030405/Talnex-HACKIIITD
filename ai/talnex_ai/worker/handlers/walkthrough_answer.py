"""Job `walkthrough_answer`: answer one question a reviewer asked about a feature (architecture section 31).

Added by the Go API with no pipeline (input {"walkthrough_id": ...}), so finishing it never starts another stage. Works for a
hackathon project and a project on a resume alike. Status: queued -> answering -> done | failed.

A recorded question is turned into text first, then its audio is deleted from storage at once and `audio_key` cleared.
Safe to run twice: a question already answered is left as it is, and text already made from a recording is not made again.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.claims.store import Subject
from talnex_ai.db.jobs import Job
from talnex_ai.reports.walkthrough import answer_question
from talnex_ai.reports.walkthrough.transcribe import get_transcriber
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info

log = logging.getLogger("talnex.walkthrough")


def _load(pool: ConnectionPool, walkthrough_id: str) -> Optional[dict]:
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT project_id::text, candidate_project_id::text, claim_id::text, question, audio_key, status
                 FROM walkthroughs WHERE id = %s::uuid""", (walkthrough_id,)).fetchone()
    if row is None:
        return None
    project, candidate_project, claim, question, audio_key, status = row
    kind, subject_id = ("project", project) if project else ("candidate_project", candidate_project)
    return {"kind": kind, "subject_id": subject_id, "claim_id": claim, "question": question, "audio_key": audio_key,
            "status": status}


def _previous_claim(pool: ConnectionPool, kind: str, subject_id: str, walkthrough_id: str) -> Optional[str]:
    """The feature of the reviewer's last answered question on this project, for follow-ups ("what if it fails?")."""
    column = "project_id" if kind == "project" else "candidate_project_id"
    with pool.connection() as conn:
        row = conn.execute(
            f"""SELECT claim_id::text FROM walkthroughs
                 WHERE {column} = %s::uuid AND id <> %s::uuid AND status = 'done' AND claim_id IS NOT NULL
                   AND created_at <= (SELECT created_at FROM walkthroughs WHERE id = %s::uuid)
                 ORDER BY created_at DESC LIMIT 1""", (subject_id, walkthrough_id, walkthrough_id)).fetchone()
    return row[0] if row else None


def _set(pool: ConnectionPool, walkthrough_id: str, sql: str, params: tuple = ()) -> None:
    with pool.connection() as conn:
        conn.execute(f"UPDATE walkthroughs SET {sql} WHERE id = %s::uuid", (*params, walkthrough_id))


def _question_text(sv, walkthrough_id: str, row: dict) -> str:
    """The typed question, or the text of the recording. The recording is deleted as soon as its text is saved."""
    key = row["audio_key"]
    if not key:
        return (row["question"] or "").strip()
    question = (row["question"] or "").strip()
    if not question:   # not made yet (a retry after the text was saved skips straight to deleting)
        question = get_transcriber(sv.cfg.walkthrough)(sv.files.get_bytes(key)).strip()
        _set(sv.pool, walkthrough_id, "question = %s", (question,))
    try:
        sv.files.delete(key)
    except Exception:
        log.warning("walkthrough %s: could not delete the recording; it will be tried again", walkthrough_id, exc_info=True)
        raise
    _set(sv.pool, walkthrough_id, "audio_key = NULL")
    return question


def _drop_audio(sv, walkthrough_id: str, key: str) -> None:
    try:
        sv.files.delete(key)
        _set(sv.pool, walkthrough_id, "audio_key = NULL")
    except Exception:
        log.exception("walkthrough %s: could not delete the recording %s", walkthrough_id, key)


@stage("walkthrough_answer")
def walkthrough_answer(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    walkthrough_id = str(job.input.get("walkthrough_id") or "")
    if not walkthrough_id:
        raise ValueError("walkthrough_answer needs a walkthrough_id")
    row = _load(ctx.pool, walkthrough_id)
    if row is None:
        return {"skipped": True, "reason": "the question no longer exists"}
    if row["status"] == "done":
        return {"walkthrough_id": walkthrough_id, "status": "done", "already_answered": True}

    sv = get_services(ctx.pool)
    _set(ctx.pool, walkthrough_id, "status = 'answering', error = NULL")
    try:
        question = _question_text(sv, walkthrough_id, row)
        ctx.check()
        if not question:
            _set(ctx.pool, walkthrough_id, "status = 'failed', error = %s",
                 ("No words could be made out in the recording. Please ask again.",))
            return {"walkthrough_id": walkthrough_id, "status": "failed", "reason": "empty question"}
        info = load_subject_info(ctx.pool, Subject(row["kind"], row["subject_id"]))  # type: ignore[arg-type]
        answer = answer_question(
            ctx.pool, sv.model, sv.cfg.walkthrough, kind=row["kind"], subject_id=row["subject_id"], repo_url=info.repo_url,
            question=question, claim_id=row["claim_id"],
            previous_claim_id=_previous_claim(ctx.pool, row["kind"], row["subject_id"], walkthrough_id), job_id=job.id)
        ctx.check()
    except Exception as exc:
        last_try = job.tries >= job.max_tries
        if last_try and row["audio_key"]:
            _drop_audio(sv, walkthrough_id, row["audio_key"])   # a recording is never kept, even when no answer came
        _set(ctx.pool, walkthrough_id, "status = %s, error = %s",
             ("failed" if last_try else "queued", "The answer could not be made." if last_try else f"retrying: {type(exc).__name__}"))
        raise

    _set(ctx.pool, walkthrough_id, "status = 'done', answer = %s::jsonb, claim_id = %s::uuid, answered_at = now(), error = NULL",
         (json.dumps(answer), answer.get("claim_id")))
    return {"walkthrough_id": walkthrough_id, "status": "done", "claim_id": answer.get("claim_id"),
            "choices": len(answer.get("choices") or []), "not_found": answer.get("not_found")}
