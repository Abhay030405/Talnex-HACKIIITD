"""Code review from the cloned repository (R9 of the sandbox track, architecture 28.8 and 29.2).

For each claim, pick the few source files most likely to hold the feature (by words of the claim found in paths and in the code,
searched inside the VM), read them, and ask a model whether the claimed mechanism is really written and how well. The answer
is evidence with file and line references, labelled "reviewed from code, not run". A mechanism that is plainly missing from
the code scores 0 (rule 17); a mechanism we simply could not find in the files we read is "unclear", never a mark against the team.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.checks.sponsor_usage import candidate_source_files
from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.code_reviewer import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.sandbox.client import ExecResult
from talnex_ai.sandbox.stack_detect.gather import REPO_DIR, read_files

_STOP = {"that", "this", "with", "from", "into", "their", "there", "have", "which", "when", "your", "users", "user", "using", "uses",
         "able", "also", "each", "every", "feature", "page", "app", "application", "project", "system", "support", "supports", "allow",
         "allows", "should", "will", "make", "makes", "show", "shows", "list", "view", "views", "get", "gets", "can", "has", "they",
         "them", "then", "than", "over", "only", "like", "such", "more", "most", "some", "any", "all", "the", "and", "for", "are"}
MAX_TOKENS = 6
_WORD = re.compile(r"[A-Za-z][A-Za-z_]{3,}")


class VmLike(Protocol):
    def exec(self, command: str, **kwargs) -> ExecResult: ...


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file: str = Field(default="", max_length=300)
    line: Optional[int] = Field(default=None, ge=1)
    what: str = Field(default="", max_length=300)


class _Quality(BaseModel):
    model_config = ConfigDict(extra="ignore")
    good: bool = True
    point: str = Field(default="", max_length=300)
    file: str = Field(default="", max_length=300)
    line: Optional[int] = Field(default=None, ge=1)


class _AiNotes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    is_ai_feature: bool = False
    model_call: Optional[bool] = None
    error_handling: Optional[bool] = None
    output_validated: Optional[bool] = None
    keys_from_environment: Optional[bool] = None


class Finding(BaseModel):
    """What the review found for one claim."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    mechanism: Literal["present", "partial", "missing", "unclear"]
    evidence: list[_Evidence] = Field(default_factory=list, max_length=12)
    quality: list[_Quality] = Field(default_factory=list, max_length=12)
    ai: _AiNotes = Field(default_factory=_AiNotes)
    summary: str = Field(default="", max_length=600)


@dataclass(frozen=True)
class Chosen:
    paths: list[str]
    all_source_shown: bool        # every source file of the app was shown, so "missing" is a fair thing to say


def claim_words(text: str) -> list[str]:
    """The words of a claim worth looking for in the code, most specific (longest) first."""
    seen: list[str] = []
    for w in _WORD.findall(text):
        w = w.lower().rstrip("s") if len(w) > 5 else w.lower()
        if w not in _STOP and w not in seen:
            seen.append(w)
    return sorted(seen, key=lambda w: -len(w))[:MAX_TOKENS]


def choose_files(vm: VmLike, claim_text: str, files: Sequence[str], app_dir: str, *, linked_files: Sequence[str] = (), max_files: int = 12) -> Chosen:
    """The source files most likely to hold the claimed feature. Words of the claim are searched for inside the VM."""
    prefix = f"{app_dir}/" if app_dir else ""
    pool = [f for f in files if f.startswith(prefix)]
    source = candidate_source_files(pool, limit=100_000)
    if not source:
        return Chosen([], True)
    score: dict[str, float] = {f: 0.0 for f in source}
    words = claim_words(claim_text)
    for w in words:
        for f in source:
            if w in f.lower():
                score[f] += 3
        res = vm.exec(f"cd {REPO_DIR} && grep -rIli --include='*' -e {shlex.quote(w)} {shlex.quote(prefix or '.')} 2>/dev/null | head -n 60", timeout_seconds=30)
        for line in res.stdout.splitlines():
            f = line.strip().removeprefix("./")
            if f in score:
                score[f] += 1
    for f in linked_files:
        full = f"{prefix}{f}" if prefix and not f.startswith(prefix) else f
        if full in score:
            score[full] += 5
    for f in source:  # an entry or routes file often wires a feature in, so it gets a small lift
        if PurePosixPath(f).stem.lower() in ("app", "main", "index", "server", "routes", "urls", "views", "api"):
            score[f] += 0.5
    ranked = sorted(source, key=lambda f: (-score[f], f.count("/"), f))
    chosen = [f for f in ranked if score[f] > 0][:max_files] or ranked[:max_files]
    return Chosen(chosen, len(source) <= max_files)


def review_claim(
    model: ChatClient,
    vm: VmLike,
    claim_text: str,
    files: Sequence[str],
    app_dir: str,
    *,
    linked_files: Sequence[str] = (),
    max_files: int = 12,
    max_kb: int = 120,
    job_id: Optional[str] = None,
) -> tuple[Finding, Chosen]:
    chosen = choose_files(vm, claim_text, files, app_dir, linked_files=linked_files, max_files=max_files)
    if not chosen.paths:
        return Finding(mechanism="unclear", summary="no source files were found to read"), chosen
    per_file = max(2000, (max_kb * 1024) // max(1, len(chosen.paths)))
    texts = read_files(vm, chosen.paths, max_bytes=per_file)  # type: ignore[arg-type]
    texts = {p: t for p, t in texts.items() if t.strip()}
    if not texts:
        return Finding(mechanism="unclear", summary="the chosen files could not be read"), chosen
    finding = ask_json(model, "agent", SYSTEM, build_user(claim_text, texts, files, chosen.all_source_shown),
                       lambda text: parse_model(Finding, text), job_id=job_id, max_tokens=5000)
    # Plainly missing is a strong thing to say: it needs us to have shown all the source, or at least the files that matched.
    if finding.mechanism == "missing" and not chosen.all_source_shown and not _matched_something(claim_text, texts):
        finding = finding.model_copy(update={"mechanism": "unclear",
                                             "summary": (finding.summary + " (Not enough of the code was read to say it is missing.)").strip()})
    return finding, chosen


def _matched_something(claim_text: str, texts: dict[str, str]) -> bool:
    words = claim_words(claim_text)
    return any(w in t.lower() for t in texts.values() for w in words)


def evidence_text(finding: dict) -> str:
    """A code-review finding as plain text for the score stage, always labelled as read from the code and not run."""
    word = {"present": "is there", "partial": "is only partly there", "missing": "was NOT found in the code", "unclear": "could not be judged from the code we read"}
    lines = [f"Code review (read from the code, not run): the claimed mechanism {word.get(finding.get('mechanism', 'unclear'), 'could not be judged')}."]
    if finding.get("summary"):
        lines.append(finding["summary"])
    if not finding.get("all_source_shown", True) and finding.get("mechanism") == "missing":
        lines.append("(Only some of the code was read.)")
    for e in (finding.get("evidence") or [])[:6]:
        lines.append(f"  evidence: {e.get('file', '?')}:{e.get('line', '?')} {e.get('what', '')}")
    for q in (finding.get("quality") or [])[:6]:
        lines.append(f"  {'good' if q.get('good', True) else 'weak'}: {q.get('point', '')} ({q.get('file', '?')}:{q.get('line', '?')})")
    ai = finding.get("ai") or {}
    if ai.get("is_ai_feature"):
        def yn(v):
            return "unknown" if v is None else ("yes" if v else "no")
        lines.append(f"  AI part: model call found: {yn(ai.get('model_call'))}; errors handled: {yn(ai.get('error_handling'))}; "
                     f"output checked before use: {yn(ai.get('output_validated'))}; keys from the environment: {yn(ai.get('keys_from_environment'))}")
    return "\n".join(lines)
