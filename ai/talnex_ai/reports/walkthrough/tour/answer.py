"""Answer one tour message: the guide reads the code in a read-only VM, plain code checks its plan, and the driver
shows each step on the live site while the page streams what is said (architecture section 32).

    code in the VM (once per chat) -> guide agent reads and writes the plan -> check against the real code
    -> for each step: say it, show the code, show it on the live site -> save the answer

Nothing here tests the project: no verdict, no points. The only flag a tour can raise is the one section 31.2
asks for: text aimed at an AI found in the code."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from talnex_ai.claims.store import Subject
from talnex_ai.live import Emitter
from talnex_ai.login.ladder import build_way_in
from talnex_ai.reports.walkthrough import claims_of
from talnex_ai.reports.walkthrough.check import LABEL
from talnex_ai.reports.walkthrough.evidence import repo_of
from talnex_ai.reports.walkthrough.tour.check import CheckedStep, Snippet, check_plan
from talnex_ai.reports.walkthrough.tour.driver import TourBrowser
from talnex_ai.reports.walkthrough.tour.guide import GuideError, run_guide
from talnex_ai.safety.hidden_instructions.rendered import orders_in_hidden_text
from talnex_ai.sandbox.code_vm import CODE_DIR, CodeReadError, CodeVm, fetch_repo
from talnex_ai.sandbox.stack_detect.recipe import FULL_IMAGE
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.testing.runner.executor import ExecConfig
from talnex_ai.worker.subjects import SubjectInfo, load_subject_info

log = logging.getLogger("talnex.tour")

VM_MARGIN = timedelta(minutes=2)  # a VM that dies sooner than this is replaced rather than reused
NO_CODE = "There is no code link for this project, so I can't explain how it was built."
NO_LIVE = "There is no live link for this project, so this tour is from the code only (reviewed from code, not run)."


@dataclass
class Message:
    id: str
    session_id: str
    question: str
    kind: str          # project or candidate_project
    subject_id: str
    vm_id: Optional[str]
    vm_expires_at: Optional[datetime]
    commit: Optional[str]
    status: str


def load_message(pool, message_id: str) -> Optional[Message]:
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT m.id::text, m.session_id::text, m.question, s.project_id::text, s.candidate_project_id::text,
                      s.vm_id, s.vm_expires_at, s.commit_sha, m.status
                 FROM tour_messages m JOIN tour_sessions s ON s.id = m.session_id WHERE m.id = %s::uuid""",
            (message_id,)).fetchone()
    if row is None:
        return None
    mid, sid, question, project, candidate, vm_id, expires, commit, status = row
    kind, subject = ("project", project) if project else ("candidate_project", candidate)
    return Message(mid, sid, question, kind, subject, vm_id, expires, commit, status)


def _history(pool, session_id: str, before: str) -> list[str]:
    """What was asked and said earlier in this chat, so a follow-up ("where is the login check?") makes sense."""
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT question, answer FROM tour_messages WHERE session_id = %s::uuid AND status = 'done' AND id <> %s::uuid
                ORDER BY created_at""", (session_id, before)).fetchall()
    out: list[str] = []
    for question, answer in rows:
        said = " ".join(str(item.get("text", "")) for item in (answer or {}).get("say", []))[:600]
        out += [f"Reviewer: {question}", f"You said: {said}"]
    return out


def _set_status(pool, message_id: str, status: str, **fields: Any) -> None:
    sets = ["status = %s"] + [f"{name} = %s{'::jsonb' if name == 'answer' else ''}" for name in fields]
    params = [status] + [json.dumps(v) if name == "answer" else v for name, v in fields.items()]
    if status in ("done", "failed"):
        sets.append("answered_at = now()")
    with pool.connection() as conn:
        conn.execute(f"UPDATE tour_messages SET {', '.join(sets)} WHERE id = %s::uuid", (*params, message_id))


def browser_runs_left(pool, info: SubjectInfo, limit: int) -> int:
    """Agent runs this project may still use: the tests' live runs and the tours' browser sessions share the limit."""
    column = "project_id" if info.kind == "project" else "candidate_project_id"
    with pool.connection() as conn:
        tests = conn.execute(
            f"""SELECT count(*) FROM test_runs r JOIN claims c ON c.id = r.claim_id
                 WHERE r.track = 'live' AND c.{column} = %s::uuid""", (info.id,)).fetchone()[0]
        tours = conn.execute(f"SELECT coalesce(sum(browser_runs), 0) FROM tour_sessions WHERE {column} = %s::uuid",
                             (info.id,)).fetchone()[0]
    return max(0, limit - int(tests) - int(tours))


def ensure_code_vm(sv, msg: Message, repo: str, emit: Callable[..., None]) -> tuple[CodeVm, Optional[str]]:
    """The chat's code VM: the live one if it still has time left, else a fresh VM with the code in it.
    Raises CodeReadError (with the reason) when the code cannot be had."""
    now = datetime.now(timezone.utc)
    if msg.vm_id and msg.vm_expires_at and msg.vm_expires_at - now > VM_MARGIN:
        return CodeVm(sv.sandbox.attach(msg.vm_id)), msg.commit
    if sv.sandbox is None or not sv.cfg.sandbox.url:
        raise CodeReadError("the code reader is not set up on this server")
    cfg = sv.cfg.tour
    emit("tour.status", text="Getting the project's code ready to read")
    archive, commit = fetch_repo(repo, msg.commit, max_mb=cfg.repo_max_mb, file_max_kb=cfg.file_max_kb,
                                 max_files=cfg.max_files)
    seconds = cfg.vm_minutes * 60
    try:
        vm = sv.sandbox.open_vm(FULL_IMAGE, time_limit_seconds=seconds)
    except Exception as err:  # a host that is down or full is our trouble, said plainly
        raise CodeReadError("the code reader is busy right now; try again in a minute") from err
    try:
        vm.upload(archive, CODE_DIR)
    except Exception as err:
        try:
            vm.destroy()
        except Exception:
            pass
        raise CodeReadError("the code could not be put in the reader") from err
    with sv.pool.connection() as conn:
        conn.execute("UPDATE tour_sessions SET vm_id = %s, vm_expires_at = %s, commit_sha = %s WHERE id = %s::uuid",
                     (vm.id, now + timedelta(seconds=seconds), commit, msg.session_id))
    return CodeVm(vm), commit


def _proof_json(snippet: Snippet) -> dict:
    return {"kind": "code", "file": snippet.file, "start": snippet.start, "end": snippet.end, "commit": snippet.commit,
            "url": snippet.url, "lines": snippet.lines}


def _snippet_event(snippet: Snippet) -> dict:
    return {"file": snippet.file, "start": snippet.start, "end": snippet.end, "commit": snippet.commit,
            "url": snippet.url, "lines": snippet.lines[:25]}


def answer_message(sv, message_id: str, *, job_id: Optional[str] = None, check_time: Callable[[], None] = lambda: None) -> dict:
    """Do the whole tour message. Always leaves the message 'done' or 'failed', never 'working'."""
    pool = sv.pool
    msg = load_message(pool, message_id)
    if msg is None:
        return {"skipped": True, "reason": "the message does not exist"}
    if msg.status == "done":
        return {"skipped": True, "reason": "already answered"}
    info = load_subject_info(pool, Subject(msg.kind, msg.subject_id))
    emitter = Emitter(pool, msg.kind, msg.subject_id, job_id=job_id, stage="tour_message", tour_id=msg.session_id,
                      message_id=msg.id)
    _set_status(pool, msg.id, "working")
    emitter.emit("tour.started", question=msg.question)
    try:
        answer = _answer(sv, msg, info, emitter, job_id, check_time)
    except Exception as err:
        log.exception("tour message %s failed", message_id)
        _set_status(pool, msg.id, "failed", error="The guide hit a problem on our side. Please ask again.")
        emitter.emit("tour.notice", text="The guide hit a problem on our side. Please ask again.")
        emitter.emit("tour.done", status="failed")
        raise
    _set_status(pool, msg.id, "done", answer=answer)
    emitter.emit("tour.done", status="done")
    return {"steps": len(answer["say"]), "mode": answer["mode"]}


def _answer(sv, msg: Message, info: SubjectInfo, emitter, job_id, check_time) -> dict:
    pool, cfg = sv.pool, sv.cfg
    repo = repo_of(info.repo_url)
    has_live = bool(info.live_url)
    said: list[dict] = []
    mode = "full" if repo and has_live else "code_only" if repo else "live_only"

    def flag_hidden_text(text: str) -> None:
        try:
            for finding in orders_in_hidden_text([text]):
                add_flag(pool, info.kind, info.id, "hidden_ai_instructions", "strong",
                         "Text aimed at an AI reviewer was found in the project's code", finding.as_flag_evidence())
        except Exception:
            log.warning("hidden text check of the code failed", exc_info=True)

    steps: list[CheckedStep] = []
    if repo is None:
        steps = [CheckedStep(NO_CODE + " Here is the live site as a visitor sees it.", [], "open the site", None)]
    else:
        try:
            code, commit = ensure_code_vm(sv, msg, repo, emitter.emit)
            check_time()
            emitter.emit("tour.status", text="Reading the code")
            plan = run_guide(
                sv.model, code, question=msg.question, claims=[c.text for c in claims_of(pool, info.kind, info.id)],
                has_live=has_live, history=_history(pool, msg.session_id, msg.id),
                max_calls=cfg.tour.guide_max_tool_calls, job_id=job_id,
                on_read=lambda tool, what: emitter.emit("tour.read", tool=tool, what=what), on_code_text=flag_hidden_text)
            steps, dropped = check_plan(plan, code, repo=repo, commit=commit, snippet_lines=cfg.walkthrough.snippet_lines)
            for reason in dropped:
                log.info("tour: %s", reason)
            if not steps:
                reason = plan.not_found or "the code has no clear place for that"
                steps = [CheckedStep(f"I couldn't find that in the code: {reason}. "
                                     "Nothing here shows how it would be built.", [], None, None)]
        except (CodeReadError, GuideError) as err:
            steps = [CheckedStep(f"I couldn't read the code for this project ({err}), so I can't say how it was built.",
                                 [], "open the site" if has_live else None, None)]
            mode = "live_only" if has_live else "none"
    if not has_live:
        for step in steps:
            step.show = None  # nothing to show it on
        emitter.emit("tour.notice", text=NO_LIVE if repo else NO_CODE)

    browser: Optional[TourBrowser] = None
    note_no_browser: Optional[str] = None
    if has_live and any(s.show for s in steps):
        if browser_runs_left(pool, info, cfg.limits.max_agent_runs_per_project) <= 0:
            note_no_browser = "This project has used its browser runs, so the tour is explained from the code only."
        else:
            way_in = build_way_in(info.live_host, cfg.email, cfg.phone.number)
            exec_cfg = ExecConfig(cfg.runner.max_actions, cfg.runner.max_actions_per_step, cfg.runner.max_seconds,
                                  cfg.runner.snapshot_chars, cfg.runner.seconds_per_step)
            browser = TourBrowser(
                provider=sv.browser or sv.tinyfish, connect=sv.connect, files=sv.files, model=sv.model,
                site_url=info.live_url, subject_id=info.id, uploads_root=Path(sv.uploads_root or "."), exec_config=exec_cfg,
                max_actions=cfg.tour.max_browser_steps, job_id=job_id, way_in=way_in.instructions,
                on_event=None)
    try:
        if browser is not None:
            try:
                browser.__enter__()
                with pool.connection() as conn:
                    conn.execute("UPDATE tour_sessions SET browser_runs = browser_runs + 1 WHERE id = %s::uuid", (msg.session_id,))
            except Exception as err:
                log.warning("tour browser could not start: %s", err)
                note_no_browser = "I couldn't open the live site, so this tour is explained from the code only."
                browser = None
        for index, step in enumerate(steps, start=1):
            check_time()
            emitter.emit("tour.say", index=index, total=len(steps), text=step.say,
                         proof=[{"file": s.file, "start": s.start, "end": s.end, "url": s.url} for s in step.snippets])
            if step.snippets:
                emitter.emit("tour.code", index=index, snippets=[_snippet_event(s) for s in step.snippets])
            keys: list[str] = []
            note = " ".join(step.notes) or None
            shown: Optional[bool] = None
            if step.show:
                if browser is not None:
                    def on_event(kind: str, _index=index, **data: Any) -> None:
                        if kind == "step.record" and data.get("proof_key"):
                            keys.append(data["proof_key"])
                        emitter.emit(kind, tour_step=_index, **data)
                    browser.on_event = on_event
                    miss = browser.show(step.show, step.expect, question=msg.question)
                    shown = miss is None
                    note = miss or note
                else:
                    shown, note = False, note_no_browser or note
                if note:
                    emitter.emit("tour.notice", text=note, index=index)
            said.append({"text": step.say, "shown": shown, "note": note,
                         "proof": [_proof_json(s) for s in step.snippets] + [{"kind": "screenshot", "key": k} for k in keys[-3:]]})
    finally:
        if browser is not None:
            browser.__exit__(None, None, None)
    return {"say": said, "label": LABEL, "mode": mode}
