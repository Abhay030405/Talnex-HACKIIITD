"""The test loop: runs one plan on a page, one action at a time, with a screenshot saved at every action.

For each plan step the model looks at the page (an accessibility snapshot, plus a screenshot only when
the text isn't enough), picks ONE action, plain code checks it's safe, the driver does it, and we look
again. When the step's expected result is visible the model says "done". At the end a separate
judgement says whether the plan's expected result happened.

Nothing here blames a site for our own trouble: running out of time or actions, a CAPTCHA, or a
refused action all end as "blocked", never "broken".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import FormatError, StepRecord, TestPlan, parse_model
from talnex_ai.llm.prompts.runner import FINAL_PARTS_SYSTEM, FINAL_SYSTEM, STEP_SYSTEM, final_parts_user, final_user, step_user
from talnex_ai.scoring.claim_points import outcome_from_parts
from talnex_ai.testing.checks import PartMark, numbered, read_marks
from talnex_ai.testing.scope import unchanged_value
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.login.email.extract import EmailHint
from talnex_ai.testing.runner.actions import (
    Decision, FinalVerdict, Navigate, ReadEmail, ReadSms, Scroll, describe, looks_like_captcha, seen_address,
    unsafe_reason,
)
from talnex_ai.testing.runner.driver import ActionError, PageDriver

log = logging.getLogger("talnex.runner")

Outcome = Literal["works", "partly_works", "broken", "blocked"]
SPARSE_SNAPSHOT = 80  # a page with less text than this probably isn't readable as text: send a picture too
CLOCK_SLACK = timedelta(seconds=60)  # messages count from a minute before the run, for clock differences


class SmsBoxLike(Protocol):
    """The team phone's texts (login/phone). Only the code is ever handed back."""

    def wait_for_code(self, since: datetime) -> Optional[Any]: ...


class MailboxLike(Protocol):
    """The sign-up inbox for one site (login/email/agentmail.py)."""

    def wait_for_hint(self, since: datetime) -> Optional[EmailHint]: ...


@dataclass(frozen=True)
class ExecConfig:
    max_actions: int = 40
    max_actions_per_step: int = 6
    max_seconds: int = 240
    snapshot_chars: int = 6000
    seconds_per_step: int = 60  # the run's limit grows with the plan: max(max_seconds, steps x seconds_per_step)


@dataclass
class ExecResult:
    outcome: Outcome
    observed: str
    records: list[StepRecord] = field(default_factory=list)
    actions_used: int = 0
    vision_used: bool = False
    stop_reason: Optional[str] = None  # set when the outcome is "blocked"
    parts: tuple[str, ...] = ()        # one mark per plan check, when the plan had checks


def trim(text: str, limit: int) -> str:
    """Cut a snapshot at a line boundary."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n[...rest of the page cut...]"


# Only real test inputs can be uploaded: pictures, documents and plain data files. A README describing the
# folder once went in as a "photo".
UPLOADABLE = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".txt", ".csv", ".json", ".docx", ".mp3", ".wav", ".mp4"}


def list_test_files(uploads_root: Path) -> list[str]:
    """The test files that really exist (paths relative to the test files folder, forward slashes)."""
    root = Path(uploads_root) / "known_answers"
    if not root.is_dir():
        return []
    return sorted(p.relative_to(uploads_root).as_posix() for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in UPLOADABLE and not p.name.lower().startswith("readme"))[:30]


INCOMPLETE = "the test could not show every part of the claim"


class _FinalParts(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    checks: list[PartMark] = Field(min_length=1)
    observed: str = Field(min_length=1, max_length=600)


def _final_parts(text: str, claim_text: str, count: int) -> tuple[tuple[str, ...], str]:
    """The run's marks for each check, and what it saw. A count or progress "seen" at its starting value is sent back."""
    answer = parse_model(_FinalParts, text)
    marks = read_marks(answer.checks, count)
    for m in answer.checks:
        start = unchanged_value(claim_text, m.note) if m.status == "seen" else None
        if start:
            raise FormatError(f'check {m.n} is marked seen, but its note describes a starting value ("{start}"), which would '
                              "look the same if the feature did nothing. Mark it not_seen, or say how the value changed.")
    return marks, answer.observed


def _final(text: str, claim_text: str) -> FinalVerdict:
    """The run's own verdict. "works" resting on a count or progress still at its starting value is sent back."""
    verdict = parse_model(FinalVerdict, text)
    start = unchanged_value(claim_text, verdict.observed) if verdict.verdict == "works" else None
    if start:
        raise FormatError(f'the verdict is works, but the value you describe ("{start}") is still at its starting point, '
                          "which would look the same if the feature did nothing. Answer partly_works or broken, unless "
                          'the test changed the value on purpose: then say how it changed ("went from 1 to 0").')
    return verdict


def _read_code(kind: str, box: Optional[Any], since: datetime) -> tuple[Optional[str], Optional[str]]:
    """Wait for a sign-up email or text. Returns (what the model is told, error). A mail or phone
    problem is ours, never the site's."""
    if box is None:
        return None, f"{'email' if kind == 'email' else 'phone sign-up'} is not set up for this run"
    try:
        found = box.wait_for_hint(since) if kind == "email" else box.wait_for_code(since)
    except Exception as err:
        log.warning("could not read the sign-up %s: %s", kind, err)
        return None, "the inbox could not be read" if kind == "email" else "the text messages could not be read"
    if kind == "email":
        if found is None or not found.found:
            return None, "no verification email with a code or link arrived in time"
        return (f"the code is {found.code}" if found.code else f"the link is {found.link}"), None
    if found is None:
        return None, "no text message with a code arrived in time"
    return f"the code is {found.code}", None


def execute_plan(
    client: ChatClient,
    driver: PageDriver,
    plan: TestPlan,
    *,
    claim_text: str,
    site_url: str,
    cfg: ExecConfig,
    uploads_root: Path,
    save_proof: Callable[[int, bytes], Optional[str]],
    way_in: Optional[str] = None,
    mailbox: Optional[MailboxLike] = None,
    smsbox: Optional[SmsBoxLike] = None,
    on_hidden_text: Optional[Callable[[list[str]], None]] = None,
    clock: Callable[[], float] = time.monotonic,
    job_id: Optional[str] = None,
    on_event: Optional[Callable[..., None]] = None,
) -> ExecResult:
    site_host = urlparse(site_url if "//" in site_url else "https://" + site_url).hostname or ""
    started = clock()
    time_limit = max(cfg.max_seconds, cfg.seconds_per_step * len(plan.steps))  # longer plans get more time
    messages_since = datetime.now(timezone.utc) - CLOCK_SLACK
    records: list[StepRecord] = []
    history: list[str] = []
    used = {"actions": 0, "vision": False}
    test_files = list_test_files(uploads_root)  # only these may be uploaded; the model never invents a file
    scanned_urls: set[str] = set()              # each page is asked for its hidden text once
    seen_text: list[str] = []                   # every page seen so far: addresses in it are ones a visitor could follow

    def tell(kind: str, **data) -> None:
        """Report progress to the live view. Watching must never change what's being watched."""
        if on_event is not None:
            try:
                on_event(kind, **data)
            except Exception as err:
                log.warning("live event %s failed: %s", kind, err)

    def finish(outcome: Outcome, observed: str, reason: Optional[str] = None) -> ExecResult:
        tell("run.outcome", outcome=outcome, observed=observed, stop_reason=reason, actions=used["actions"])
        return ExecResult(outcome, observed, records, used["actions"], used["vision"], reason)

    def record(action: str, expected: Optional[str], observed: Optional[str], box: Optional[dict] = None) -> None:
        """Save a step record with a screenshot of the page as it is right now."""
        number = len(records) + 1
        try:
            shot = driver.screenshot()
        except Exception as err:
            log.warning("could not take a screenshot: %s", err)
            shot = b""
        records.append(StepRecord(step_number=number, kind="screen", action=action, expected=expected,
                                  observed=observed, proof_key=save_proof(number, shot) if shot else None))
        tell("step.record", number=number, label=action, expected=expected, observed=observed,
             proof_key=records[-1].proof_key, box=box, url=driver.url())

    def note_last(observed: str) -> None:
        if records and observed:
            records[-1] = records[-1].model_copy(update={"observed": observed})

    def scan_hidden_text() -> None:
        url = driver.url()
        if on_hidden_text is None or url in scanned_urls:
            return
        scanned_urls.add(url)
        try:
            pieces = driver.hidden_text() if hasattr(driver, "hidden_text") else []
            if pieces:
                on_hidden_text(pieces)
        except Exception as err:  # this check must never stop the test
            log.warning("hidden text check failed: %s", err)

    for index, step in enumerate(plan.steps, start=1):
        step_actions = 0
        last_error: Optional[str] = None
        send_picture = False
        acted_in_step = False

        while True:
            if clock() - started > time_limit:
                record("Stopped: out of time", None, f"the run passed its {time_limit}s limit")
                return finish("blocked", "the test ran out of time", "ran out of time")
            if used["actions"] >= cfg.max_actions:
                record("Stopped: too many actions", None, f"the run passed {cfg.max_actions} actions")
                return finish("blocked", "the test ran out of steps", "ran out of actions")

            snapshot = trim(driver.snapshot(), cfg.snapshot_chars)
            seen_text += [snapshot, driver.url()]  # a page the site itself sent us to is a real address too
            scan_hidden_text()
            if looks_like_captcha(snapshot):
                record("Stopped: a human check appeared", step.expected, "a CAPTCHA or human check is on the page")
                return finish("blocked", "a human check (CAPTCHA) stopped the test", "a human check appeared")

            images: list[bytes] = []
            if send_picture or len(snapshot.strip()) < SPARSE_SNAPSHOT:
                try:
                    images.append(driver.screenshot())
                    used["vision"] = True
                except Exception as err:
                    log.warning("could not take a screenshot for the model: %s", err)

            decision = ask_json(
                client, "agent", STEP_SYSTEM,
                step_user(claim=claim_text, step_number=index, step_total=len(plan.steps), action=step.action,
                          expected=step.expected, way_in=way_in, history=history[-6:], url=driver.url(),
                          title=driver.title(), snapshot=snapshot, last_error=last_error, test_files=test_files),
                lambda text: parse_model(Decision, text), job_id=job_id, images=images,
            )
            if decision.thought:
                tell("reason", step=index, text=decision.thought, looked_at_picture=bool(images))

            if decision.step_result is not None:
                observed = decision.observed or decision.thought
                if acted_in_step:
                    note_last(observed)
                else:
                    record(f"Look: {step.action}", step.expected, observed)
                tell("step.result", step=index, steps=len(plan.steps), result=decision.step_result, observed=observed)
                if decision.step_result == "blocked":
                    history.append(f"Step {index} blocked: {observed}")
                    return finish("blocked", observed or "the test was blocked", "blocked by the site")
                history.append(f"Step {index} {'FAILED' if decision.step_result == 'failed' else 'done'}: {observed}")
                break

            action = decision.action
            step_actions += 1
            if step_actions > cfg.max_actions_per_step:
                history.append(f"Step {index} FAILED: still not done after {cfg.max_actions_per_step} actions")
                note_last("gave up on this step after too many actions")
                break

            refusal = unsafe_reason(action, site_host=site_host, uploads_root=uploads_root)
            if refusal:
                record(f"Refused: {describe(action)}", step.expected, f"not done, because {refusal}")
                return finish("blocked", f"the test was stopped: {refusal}", "refused an unsafe action")

            used["actions"] += 1
            acted_in_step = True
            label = describe(action)

            if isinstance(action, (ReadEmail, ReadSms)):
                # Not a browser action: wait for the message and hand the model only its code or link.
                told, last_error = _read_code("email" if isinstance(action, ReadEmail) else "sms",
                                              mailbox if isinstance(action, ReadEmail) else smsbox, messages_since)
                if last_error is None:
                    history.append(f"{label}: {told}")
                    record(label, step.expected, "a verification code or link arrived")
                else:
                    history.append(f"{label} (did not work: {last_error})")
                    record(f"{label} (did not work: {last_error})", step.expected, last_error)
                send_picture = last_error is not None
                continue

            try:
                if isinstance(action, Navigate) and not seen_address(action.url, site_url, "\n".join(seen_text + history)):
                    raise ActionError("that address was never shown on any page. Use the links and buttons you can "
                                      "see (or the start address); do not guess pages")
                driver.perform(action, uploads_root)
                last_error = None
            except ActionError as err:
                last_error = str(err)
            if last_error is None and isinstance(action, Scroll) and trim(driver.snapshot(), cfg.snapshot_chars) == snapshot:
                # Pictures show the whole page, so scrolling only matters for content that loads as you go.
                # When nothing changed there's nothing more to find; without this the model scrolls until time runs out.
                last_error = ("scrolling changed nothing: everything on the page is already shown. Decide this step's "
                              "result from what is shown")
            if last_error:
                label = f"{label} (did not work: {last_error})"
            record(label, step.expected, last_error, box=None if last_error else getattr(driver, "last_box", None))
            history.append(label)
            send_picture = last_error is not None

    # The final judgement against the plan's expected result.
    snapshot = trim(driver.snapshot(), cfg.snapshot_chars)
    if looks_like_captcha(snapshot):
        return finish("blocked", "a human check (CAPTCHA) stopped the test", "a human check appeared")
    if plan.checks:
        marks, observed = ask_json(
            client, "agent", FINAL_PARTS_SYSTEM,
            final_parts_user(claim=claim_text, checks=numbered(plan.checks), history=history, url=driver.url(),
                             snapshot=snapshot),
            lambda text: _final_parts(text, claim_text, len(plan.checks)), job_id=job_id,
        )
        record("Final check", plan.expected_result, observed)
        outcome = outcome_from_parts(marks, [c.promise for c in plan.checks])
        done = finish(outcome, observed, INCOMPLETE if outcome == "blocked" else None)
        done.parts = marks
        return done
    verdict = ask_json(
        client, "agent", FINAL_SYSTEM,
        final_user(claim=claim_text, expected_result=plan.expected_result, history=history, url=driver.url(),
                   snapshot=snapshot),
        lambda text: _final(text, claim_text), job_id=job_id,
    )
    record("Final check", plan.expected_result, verdict.observed)
    return finish(verdict.verdict, verdict.observed, "blocked" if verdict.verdict == "blocked" else None)
