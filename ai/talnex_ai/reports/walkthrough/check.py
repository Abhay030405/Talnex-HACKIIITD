"""Plain-code checks on the model's walkthrough answer (architecture section 31.2). The model is never trusted on its own:

- a proof handle that is not in the gathered evidence (a file, a line range, a step, a screenshot that was never collected)
  is removed, and a sentence left with no proof is dropped;
- a "missing" item must be a checklist item; when the code could not be read it becomes "code_not_readable", never
  "not_found_in_code"; when scoring marked the item present, the stored result wins and the disagreement is logged.

Proof references are built here from the evidence, never copied from the model, so every link opens real lines.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from talnex_ai.reports.walkthrough.evidence import BLOB, Evidence
from talnex_ai.settings import WalkthroughSettings

log = logging.getLogger("talnex.walkthrough")

MAX_FLOW = 8
MAX_SEEN = 5
_CODE = re.compile(r"^F(\d+)(?::(\d+)(?:\s*-\s*(\d+))?)?$")


class _Sentence(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    text: str = Field(default="", max_length=600)
    proof: list[str] = Field(default_factory=list)

    @field_validator("proof", mode="before")
    @classmethod
    def _as_strings(cls, value):
        return [str(v).strip() for v in value] if isinstance(value, list) else []


class _Missing(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    item: str = Field(default="", max_length=200)
    proof: list[str] = Field(default_factory=list)

    @field_validator("proof", mode="before")
    @classmethod
    def _as_strings(cls, value):
        return [str(v).strip() for v in value] if isinstance(value, list) else []


class ModelAnswer(BaseModel):
    """What the model is asked to reply with (llm/prompts/walkthrough.py)."""

    model_config = ConfigDict(extra="ignore")
    flow: list[_Sentence] = Field(default_factory=list)
    seen: list[_Sentence] = Field(default_factory=list)
    missing: list[_Missing] = Field(default_factory=list)
    not_found: bool = False


def _code_ref(ev: Evidence, handle: str, cfg: WalkthroughSettings) -> Optional[dict]:
    m = _CODE.match(handle)
    if not m:
        return None
    f = ev.file(f"F{m.group(1)}")
    if f is None:
        return None
    start = int(m.group(2)) if m.group(2) else f.start
    end = int(m.group(3)) if m.group(3) else (start if m.group(2) else f.end)
    if not (f.start <= start <= end <= f.end):
        return None   # lines that were never read: invented
    snippet_end = min(end, start + cfg.snippet_lines - 1)
    return {"kind": "code", "path": f.path, "start": start, "end": end, "commit_sha": ev.commit_sha,
            "url": BLOB.format(repo=ev.repo, sha=ev.commit_sha, path=f.path, start=start, end=end),
            "snippet": f.text(start, snippet_end)}


def resolve(ev: Evidence, handle: str, cfg: WalkthroughSettings) -> Optional[dict]:
    """The proof reference for one handle, or None when the evidence has no such thing."""
    handle = handle.strip().upper().replace(" ", "")
    if handle.startswith("F"):
        return _code_ref(ev, handle, cfg)
    if handle.startswith("S"):
        step = next((s for s in ev.steps if s["handle"] == handle), None)
        return {"kind": "step", "step_id": step["step_id"]} if step else None
    if handle.startswith("P"):
        shot = next((p for p in ev.screenshots if p["handle"] == handle), None)
        return {"kind": "screenshot", "key": shot["key"]} if shot else None
    if handle.startswith("R"):
        note = next((r for r in ev.reviews if r["handle"] == handle), None)
        return {"kind": "review", "note": note["note"]} if note else None
    if handle == "A" and ev.authorship:
        return {"kind": "authorship", "claim_id": ev.claim_id}
    return None


def _refs(ev: Evidence, handles: list[str], cfg: WalkthroughSettings) -> list[dict]:
    out: list[dict] = []
    for h in handles:
        ref = resolve(ev, h, cfg)
        if ref is not None and ref not in out:
            out.append(ref)
    return out


def _sentences(ev: Evidence, items: list[_Sentence], limit: int, cfg: WalkthroughSettings, part: str) -> list[dict]:
    out = []
    for s in items:
        if not s.text:
            continue
        refs = _refs(ev, s.proof, cfg)
        if not refs:
            log.info("walkthrough %s: dropped a %s sentence with no real proof: %r", ev.claim_id, part, s.text[:120])
            continue
        out.append({"text": s.text, "proof": refs})
    return out[:limit]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def _missing(ev: Evidence, items: list[_Missing], cfg: WalkthroughSettings) -> list[dict]:
    checklist = {_norm(c["text"]): c for c in ev.checklist}
    out: list[dict] = []
    seen: set[str] = set()
    for m in items:
        c = checklist.get(_norm(m.item))
        if c is None:
            log.info("walkthrough %s: dropped a missing item that is not on the checklist: %r", ev.claim_id, m.item[:120])
            continue
        if c["text"] in seen:
            continue
        if c["status"] == "present":
            # The stored result wins (section 31.2); the disagreement is kept in the log for review.
            log.warning("walkthrough %s: the answer called %r missing but scoring marked it present; showing the stored result",
                        ev.claim_id, c["text"])
            continue
        seen.add(c["text"])
        if not ev.code_readable:
            out.append({"item": c["text"], "status": "code_not_readable", "proof": []})
        else:
            out.append({"item": c["text"], "status": "not_found_in_code",
                        "proof": [r for r in _refs(ev, m.proof, cfg) if r["kind"] in ("code", "review")]})
    return out


def _brief(text: Optional[str], limit: int = 300) -> str:
    one = " ".join((text or "").split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


def notes(ev: Evidence) -> list[str]:
    """What the answer must say when the evidence is thin, or when the feature did not pass (section 31.4). Plain code, never the
    model: the stored result and a failed step are said every time, so an explanation of how the code is meant to work can never
    hide that the feature failed its test."""
    out = []
    if ev.verdict == "broken":
        out.append(f"TalNex's test found this feature broken ({ev.confidence} confidence): {_brief(ev.reason) or 'no reason was recorded'}.")
    elif ev.verdict == "partly_works":
        out.append(f"TalNex's test found this feature only partly working ({ev.confidence} confidence): {_brief(ev.reason) or 'no reason was recorded'}.")
    elif ev.verdict == "reviewed_from_code" and ev.score_reason:
        out.append(f"Its score: {_brief(ev.score_reason)}.")
    failed = [s for s in ev.steps if (s.get("observed") or "").lower().startswith("fail")]
    for step in failed[:2]:
        out.append(f"A test step failed: {_brief(step.get('action'), 120)} ({_brief(step.get('observed'), 160)}).")
    if not ev.has_repo:
        out.append("There is no repo, so I can't explain the code; this is only what was seen on screen.")
    elif not ev.code_readable:
        out.append(f"I could not read the code for this feature ({ev.code_problem}), so I can't say what is missing.")
    if ev.reviewed_from_code and ev.code_readable:
        out.append("This part was reviewed from code, not run.")
    if not ev.testable:
        out.append(f"This claim can't be checked by using the app: {ev.untestable_reason or 'it is not something a visitor can try'}.")
    elif ev.verdict == "could_not_test":
        out.append(f"This feature could not be tested: {ev.reason or 'no reason was recorded'}.")
    return out


NOT_FOUND = "I couldn't find that in the code or the tests."
LABEL = "AI explanation of the evidence — the proof is in the links."


def build_answer(ev: Evidence, model: ModelAnswer, cfg: WalkthroughSettings) -> dict:
    flow = _sentences(ev, model.flow, MAX_FLOW, cfg, "flow")
    seen = _sentences(ev, model.seen, MAX_SEEN, cfg, "seen")
    missing = _missing(ev, model.missing, cfg)
    not_found = bool(model.not_found) or not (flow or seen)

    said = notes(ev)
    said += [s["text"] for s in flow] + [s["text"] for s in seen]
    really_missing = [m["item"] for m in missing if m["status"] == "not_found_in_code"]
    if really_missing:
        said.append("Missing: " + "; ".join(really_missing) + ".")
    if not_found:
        said.append(NOT_FOUND)
    return {"claim_id": ev.claim_id, "claim_text": ev.claim_text, "choices": [], "flow": flow, "seen": seen,
            "missing": missing, "not_found": not_found, "spoken": " ".join(said), "label": LABEL}


def choices_answer(choices: list, no_match: bool) -> dict:
    """The answer when the question matched no claim or several: ask which one is meant."""
    ask = "Which feature do you mean? " + "; ".join(c.text for c in choices) + "." if choices else ""
    spoken = (NOT_FOUND + " " + ask).strip() if no_match else ask
    return {"claim_id": None, "claim_text": None, "choices": [{"claim_id": c.id, "text": c.text} for c in choices],
            "flow": [], "seen": [], "missing": [], "not_found": no_match, "spoken": spoken, "label": LABEL}
