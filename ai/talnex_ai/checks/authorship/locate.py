"""Code locate (authorship proof, A1, architecture 30.3): map each claim to the files and line ranges that make the feature work.

Sources, in order of trust:
  1. the sandbox route mapping (28.6): the route that serves the claim and the handler behind it,
  2. code structure (`symbols.py`): functions, classes, components and routes whose names and files match the claim,
  3. one model call per claim, only when the first two are unclear: it reads the likely files and picks the line ranges, with a confidence.

Starter templates, library and vendor folders, lock files and generated files are removed first, with the same list the copy detector
uses. A claim whose code is not found with enough confidence becomes "could not trace: code not found", never a mark against anyone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.checks.authorship.symbols import Symbol, claim_words, symbols, words_of
from talnex_ai.checks.copy_between_teams.fingerprint import wanted
from talnex_ai.claims.from_code import feature_files
from talnex_ai.formats import Claim
from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.code_locator import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, StructuredError, ask_json

LOCATOR_ROLE = "claim_reader"   # a strong text model reading code, like the feature finder
ROUTE_CONFIDENCE = 0.9          # a route the sandbox called and linked to the claim
STRUCTURE_MIN_SCORE = 1.5       # e.g. a claim word in a symbol's name plus one in its file path (a word in the path alone counts half)
STRUCTURE_MAX_FILES = 3         # matches spread over more files than this are unclear: the model decides
MODEL_FILES = 4                 # files the model reads for one claim
MODEL_MAX_LINES = 300           # lines of each file shown to the model
_TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "cypress", "__mocks__", "fixtures"}

NOT_FOUND = "code not found"
TOO_LARGE = "repo too large"
NOT_REACHABLE = "repo not reachable"


@dataclass
class CodeMap:
    claim_id: str
    files: list[dict] = field(default_factory=list)      # [{"path", "start", "end", "why"}]
    found_by: Optional[str] = None                       # route_mapping / code_structure / model
    confidence: Optional[float] = None
    not_traced_reason: Optional[str] = None

    def as_json(self) -> dict:
        return {"claim_id": self.claim_id, "files": self.files, "found_by": self.found_by,
                "confidence": self.confidence, "not_traced_reason": self.not_traced_reason}


class _Range(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    path: str = Field(min_length=1, max_length=400)
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    why: str = Field(default="", max_length=300)


class Located(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    files: list[_Range] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    not_found_reason: Optional[str] = Field(default=None, max_length=300)


def code_files(files: Sequence[str]) -> list[str]:
    """The repo's own code: the copy detector's removal list (vendor, build, lock, minified, generated), and no test files."""
    out = []
    for f in files:
        parts = {p.lower() for p in PurePosixPath(f).parts[:-1]}
        name = PurePosixPath(f).name.lower()
        if wanted(f) and not parts & _TEST_PARTS and ".test." not in name and ".spec." not in name and not name.startswith("test_"):
            out.append(f)
    return out


def _path_words(path: str) -> set[str]:
    p = PurePosixPath(path)
    return words_of(" ".join([*p.parent.parts, p.stem]))


def score_symbol(sym: Symbol, keywords: set[str]) -> float:
    """How well a symbol matches a claim: one point per claim word in its name, half a point per claim word in its file path."""
    return len(keywords & sym.words) + 0.5 * len(keywords & _path_words(sym.path))


def _merge(ranges: list[dict]) -> list[dict]:
    """Overlapping or touching ranges in one file become one range, in file and line order."""
    out: list[dict] = []
    for r in sorted(ranges, key=lambda r: (r["path"], r["start"], r["end"])):
        last = out[-1] if out else None
        if last and last["path"] == r["path"] and r["start"] <= last["end"] + 1:
            last["end"] = max(last["end"], r["end"])
        else:
            out.append(dict(r))
    return out


def by_structure(claim: Claim, syms: Sequence[Symbol], max_files: int) -> Optional[tuple[list[dict], float]]:
    """Line ranges from the symbols that clearly match the claim, with a confidence, or None when the match is unclear."""
    keywords = claim_words(claim.text)
    if not keywords:
        return None
    scored = sorted(((score_symbol(s, keywords), s) for s in syms), key=lambda t: (-t[0], t[1].path, t[1].start))
    if not scored or scored[0][0] < STRUCTURE_MIN_SCORE:
        return None
    best = scored[0][0]
    chosen = [s for score, s in scored if score >= max(STRUCTURE_MIN_SCORE, best - 0.5)]
    # A whole-file entry is only kept when nothing more precise in that file matched.
    precise_paths = {s.path for s in chosen if s.kind != "file"}
    chosen = [s for s in chosen if s.kind != "file" or s.path not in precise_paths]
    if len({s.path for s in chosen}) > STRUCTURE_MAX_FILES:
        return None
    ranges = _merge([{"path": s.path, "start": s.start, "end": s.end, "why": f"{s.kind} {s.name.split()[0]} matches the claim"}
                     for s in chosen])
    return ranges[:max_files], round(min(0.9, 0.4 + 0.15 * best), 2)


def by_routes(claim_id: str, discovery: Mapping[str, Any], app_dir: str, known: set[str], texts: Mapping[str, str],
              max_files: int) -> list[dict]:
    """Line ranges for the routes the sandbox linked to this claim: the smallest symbol around each route's line."""
    routes = discovery.get("routes") or []
    out = []
    for index in (discovery.get("links") or {}).get(claim_id) or []:
        if not isinstance(index, int) or not 0 <= index < len(routes):
            continue
        route = routes[index] or {}
        rel, line = route.get("file") or "", int(route.get("line") or 0)
        path = f"{app_dir}/{rel}" if app_dir and rel else rel
        if not path or path not in known or line < 1:
            continue
        text = texts.get(path)
        start, end = line, line
        if text:
            around = [s for s in symbols(path, text) if s.start <= line <= s.end and s.kind != "file"]
            if around:
                inner = min(around, key=lambda s: (s.end - s.start, -s.start))
                start, end = inner.start, inner.end
        label = f"{route.get('method') or ''} {route.get('path') or ''}".strip()
        out.append({"path": path, "start": start, "end": end, "why": f"the route {label} serves this claim (sandbox route mapping)"})
    return _merge(out)[:max_files]


def by_model(model: ChatClient, claim: Claim, files: Sequence[tuple[str, str]], max_files: int,
             job_id: Optional[str] = None) -> tuple[list[dict], float, Optional[str]]:
    """One low-temperature call: the model picks line ranges in the files it was shown. Anything outside them is dropped."""
    answer = ask_json(model, LOCATOR_ROLE, SYSTEM, build_user(claim.text, files, max_lines=MODEL_MAX_LINES),
                      lambda text: parse_model(Located, text), job_id=job_id, max_tokens=1500, temperature=0.0)
    lengths = {p: min(len(t.splitlines()), MODEL_MAX_LINES) for p, t in files}
    ranges = []
    for r in answer.files:
        n = lengths.get(r.path)
        if not n or r.start > n:
            continue
        start, end = min(r.start, r.end), min(max(r.start, r.end), n)
        ranges.append({"path": r.path, "start": start, "end": end, "why": r.why or "picked by the code locator"})
    return _merge(ranges)[:max_files], float(answer.confidence), answer.not_found_reason


def files_to_read(claims: Sequence[Claim], code: Sequence[str], route_files: Sequence[str], limit: int) -> list[str]:
    """Route files first, then the files whose path shares the most words with any claim, then the usual feature files."""
    keywords = [claim_words(c.text) for c in claims]
    scored = []
    for f in code:
        pw = _path_words(f)
        best = max((len(k & pw) for k in keywords), default=0)
        if best:
            scored.append((-best, f.count("/"), f))
    chosen = [f for f in route_files if f in set(code)]
    for _, _, f in sorted(scored):
        if f not in chosen:
            chosen.append(f)
    for f in feature_files(code, limit):
        if f not in chosen:
            chosen.append(f)
    return chosen[:limit]


def _model_files(claim: Claim, syms: Sequence[Symbol], texts: Mapping[str, str]) -> list[tuple[str, str]]:
    """The files most likely to hold one claim's code, for the model: best symbol score per file, then the usual feature files."""
    keywords = claim_words(claim.text)
    best: dict[str, float] = {}
    for s in syms:
        best[s.path] = max(best.get(s.path, 0.0), score_symbol(s, keywords))
    ranked = [p for p, sc in sorted(best.items(), key=lambda t: (-t[1], t[0])) if sc > 0]
    for p in feature_files(list(texts), MODEL_FILES):
        if p not in ranked:
            ranked.append(p)
    return [(p, texts[p]) for p in ranked[:MODEL_FILES] if p in texts]


def locate(
    claims: Sequence[Claim],
    *,
    files: Sequence[str],
    read: Callable[[list[str]], Mapping[str, str]],
    model: Optional[ChatClient],
    locate_max_files: int,
    max_repo_files: int,
    max_claims: int,
    max_files_per_claim: int,
    min_confidence: float,
    discovery: Optional[Mapping[str, Any]] = None,
    app_dir: str = "",
    files_truncated: bool = False,
    job_id: Optional[str] = None,
    check: Callable[[], None] = lambda: None,
) -> list[CodeMap]:
    """One code map per claim (with an id). `read` turns repo paths into their text; a file it cannot read is simply missing."""
    claims = [c for c in claims if c.id]
    code = code_files(files)
    if files_truncated or len(code) > max_repo_files:
        why = f"{TOO_LARGE} (more than {max_repo_files} code files, the limit)"
        return [CodeMap(c.id or "", not_traced_reason=why) for c in claims]
    if not code:
        return [CodeMap(c.id or "", not_traced_reason=f"{NOT_FOUND} (the repository has no code files)") for c in claims]

    traced, over = claims[:max_claims], claims[max_claims:]
    out = {c.id: CodeMap(c.id or "", not_traced_reason=f"{TOO_LARGE} (only the first {max_claims} claims are traced, the limit)")
           for c in over}
    discovery = discovery or {}
    known = set(code)
    routes = discovery.get("routes") or []
    route_files = []
    for c in traced:
        for i in (discovery.get("links") or {}).get(c.id) or []:
            if isinstance(i, int) and 0 <= i < len(routes) and (routes[i] or {}).get("file"):
                rel = routes[i]["file"]
                route_files.append(f"{app_dir}/{rel}" if app_dir else rel)

    chosen = files_to_read(traced, code, route_files, locate_max_files)
    texts = {p: t for p, t in read(chosen).items() if t and t.strip()}
    check()
    if not texts:
        why = f"{NOT_REACHABLE} (the code files could not be read)"
        return [out.get(c.id) or CodeMap(c.id or "", not_traced_reason=why) for c in claims]
    syms = [s for p, t in sorted(texts.items()) for s in symbols(p, t)]

    for c in traced:
        cid = c.id or ""
        ranges = by_routes(cid, discovery, app_dir, known, texts, max_files_per_claim)
        if ranges:
            out[cid] = CodeMap(cid, ranges, "route_mapping", ROUTE_CONFIDENCE)
            continue
        found = by_structure(c, syms, max_files_per_claim)
        if found and found[1] >= min_confidence:
            out[cid] = CodeMap(cid, found[0], "code_structure", found[1])
            continue
        candidates = _model_files(c, syms, texts)
        if model is None or not candidates:
            out[cid] = CodeMap(cid, not_traced_reason=NOT_FOUND)
            continue
        try:
            picked, confidence, _reason = by_model(model, c, candidates, max_files_per_claim, job_id)
        except StructuredError:
            out[cid] = CodeMap(cid, not_traced_reason=f"{NOT_FOUND} (the code locator gave no usable answer)")
            continue
        check()
        if picked and confidence >= min_confidence:
            out[cid] = CodeMap(cid, picked, "model", round(confidence, 2))
        else:
            out[cid] = CodeMap(cid, confidence=round(confidence, 2), not_traced_reason=NOT_FOUND)
    return [out[c.id] for c in claims if c.id in out]
