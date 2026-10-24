"""Claims from the project's own code (open-theme events, and extra claims for fixed-problem ones).

Instead of reading what a team says or shows in a demo video, TalNex reads the code: the frontend pages, forms and buttons and the
backend routes they use. A model lists the features the code really implements, each with how a visitor can try it on the live site
and the file and line that show it exists. A feature whose evidence does not point at a real file we read is dropped, so nothing is
invented. The live test (and, for a backend, the sandbox tests) then check each one, and the code review can tell if it is really written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import Claim
from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.feature_finder import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.sandbox.client import ExecResult
from talnex_ai.sandbox.stack_detect.gather import read_files

CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte", ".html", ".htm", ".py", ".rb", ".php", ".go", ".java", ".kt", ".ejs", ".hbs", ".pug", ".njk", ".jinja", ".jinja2", ".cshtml", ".blade.php"}
SKIPPED_FOLDERS = {"node_modules", "vendor", "dist", "build", ".next", "out", "target", "__pycache__", ".venv", "venv", "coverage", "tests", "test", "__tests__", "spec", "e2e", "docs", "examples", "migrations", "assets", "static", "public/assets", "fixtures"}
# Names that say a file holds what a visitor sees or does, strongest first.
_HINTS = (("page", 6), ("view", 5), ("screen", 5), ("route", 5), ("router", 5), ("controller", 4), ("template", 4), ("form", 4), ("app", 3),
          ("main", 3), ("index", 3), ("dashboard", 3), ("login", 4), ("signup", 4), ("register", 4), ("auth", 3), ("component", 2), ("api", 3),
          ("handler", 3), ("urls", 4), ("server", 2), ("home", 3), ("nav", 1))
_NOISE = re.compile(r"(\.min\.|\.d\.ts$|\.config\.|\.test\.|\.spec\.|\.stories\.|^setup|^jest|^vite|^webpack|^tailwind|^postcss|^eslint|^babel)", re.IGNORECASE)


class VmLike(Protocol):
    def exec(self, command: str, **kwargs) -> ExecResult: ...


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file: str = Field(default="", max_length=300)
    line: Optional[int] = Field(default=None, ge=1)
    what: str = Field(default="", max_length=300)


class FoundFeature(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str = Field(min_length=3, max_length=300)
    claim_group: str = Field(min_length=1, max_length=60)
    importance: int = Field(default=2, ge=1, le=3)
    how_to_try: str = Field(default="", max_length=700)
    needs_login: bool = False
    evidence: list[_Evidence] = Field(default_factory=list, max_length=8)
    testable: bool = True
    untestable_reason: Optional[str] = None


class _Features(BaseModel):
    model_config = ConfigDict(extra="ignore")
    features: list[FoundFeature] = Field(default_factory=list, max_length=40)


@dataclass
class Found:
    claims: list[Claim] = field(default_factory=list)
    # claim text -> {how_to_try, needs_login, evidence}: kept in the stage result and given to the test planner
    notes: dict[str, dict] = field(default_factory=dict)
    files_read: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)      # features dropped because their evidence was not a file we read


def feature_files(files: Sequence[str], limit: int) -> list[str]:
    """The files most likely to show what a visitor can do: pages, views, templates, forms, routes and entry files first."""
    scored: list[tuple[float, str]] = []
    for f in files:
        p = PurePosixPath(f)
        if p.suffix.lower() not in CODE_SUFFIXES or {s.lower() for s in p.parent.parts} & SKIPPED_FOLDERS or _NOISE.search(p.name):
            continue
        name = (p.stem + " " + "/".join(p.parent.parts)).lower()
        score = sum(w for hint, w in _HINTS if hint in name)
        score += 2 if p.suffix.lower() in (".html", ".jsx", ".tsx", ".vue", ".svelte") else 0
        scored.append((score - 0.3 * len(p.parts), f))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [f for _, f in scored[:limit]]


def find_features(
    model: ChatClient,
    vm: VmLike,
    project_name: str,
    files: Sequence[str],
    *,
    readme: str = "",
    criteria: Sequence[str] = (),
    live_url: str = "",
    max_files: int = 25,
    max_kb: int = 200,
    max_claims: int = 12,
    job_id: Optional[str] = None,
) -> Found:
    chosen = feature_files(files, max_files)
    if not chosen:
        return Found()
    per_file = max(3000, (max_kb * 1024) // len(chosen))
    texts = {p: t for p, t in read_files(vm, chosen, max_bytes=per_file).items() if t.strip()}  # type: ignore[arg-type]
    if not texts:
        return Found()
    out = ask_json(model, "claim_reader", SYSTEM, build_user(project_name, texts, files, max_claims, criteria=criteria, readme=readme, live_url=live_url),
                   lambda text: parse_model(_Features, text), job_id=job_id, max_tokens=6000)

    known = set(files)
    result = Found(files_read=list(texts))
    groups = {"Access", "Core", "Logic", "Reliability", *criteria}
    seen: set[str] = set()
    for feature in out.features:
        # A feature must stand on code we really read: evidence that names a file we did not read is not evidence.
        evidence = [e.model_dump() for e in feature.evidence if e.file in texts or e.file in known]
        evidence = [e for e in evidence if e["file"] in texts]
        key = " ".join(feature.text.lower().split())
        if key in seen:
            continue
        if not evidence:
            result.dropped.append(feature.text)
            continue
        seen.add(key)
        testable = feature.testable or not feature.untestable_reason
        claim = Claim(
            text=feature.text[:300], claim_group=feature.claim_group if feature.claim_group in groups else "Core",
            importance=feature.importance, source="code", track="live", testable=feature.testable,
            untestable_reason=None if feature.testable else (feature.untestable_reason or "a visitor cannot try this directly"),
        )
        result.claims.append(claim)
        result.notes[claim.text] = {"how_to_try": feature.how_to_try, "needs_login": feature.needs_login, "evidence": evidence[:4]}
        if len(result.claims) >= max_claims:
            break
    return result
