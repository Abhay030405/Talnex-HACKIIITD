"""Route discovery (R4 of the sandbox track, architecture 28.6): find every route of the running backend and link routes to
the project's claims.

  1. ask the running app for an OpenAPI document (/openapi.json and a few usual places),
  2. read route definitions from the team's source files in the VM,
  3. read the endpoints listed in the README,
  4. merge the three, and let a model link routes to claims and mark which routes need a token or a body.

A route found only in the code is a candidate; the test stage proves it by calling it. Routes that serve no claim become
minor claims ("responds sensibly", importance 1) so every route gets a smoke test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.checks.sponsor_usage import candidate_source_files
from talnex_ai.formats import Claim
from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.route_mapper import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, StructuredError, ask_json
from talnex_ai.sandbox.client import ExecResult, HttpResult
from talnex_ai.sandbox.route_discovery.extract import FoundRoute, from_code, from_openapi, from_readme, merge
from talnex_ai.sandbox.stack_detect.detect import RepoFacts
from talnex_ai.sandbox.stack_detect.gather import read_files

SPEC_PATHS = ("/openapi.json", "/swagger.json", "/v3/api-docs", "/api-docs", "/api/openapi.json", "/docs/openapi.json", "/api/swagger.json")
MAX_SOURCE_FILES = 60
MAX_ROUTES_FOR_MODEL = 120
MAX_MINOR_CLAIMS = 25
# Paths that every app has and that say nothing about the project's own work.
PLUMBING = {"/", "/health", "/healthz", "/ping", "/status", "/favicon.ico", "/docs", "/redoc", "/openapi.json", "/swagger.json",
            "/api/health", "/robots.txt"}
_ROUTE_HINTS = ("route", "router", "api", "controller", "view", "handler", "endpoint", "urls", "app", "server", "main", "index")


class DiscoveryVm(Protocol):
    def exec(self, command: str, **kwargs) -> ExecResult: ...
    def request(self, method: str, port: int, path: str, **kwargs) -> HttpResult: ...


@dataclass
class Route:
    method: str
    path: str
    source: str
    file: str = ""
    line: int = 0
    summary: str = ""
    body_fields: list[str] = field(default_factory=list)
    needs_auth: Optional[bool] = None
    purpose: str = ""

    def label(self) -> str:
        return f"{self.method} {self.path}"


@dataclass
class Discovery:
    routes: list[Route] = field(default_factory=list)
    links: dict[str, list[int]] = field(default_factory=dict)      # claim id -> indexes into routes
    minor_claims: list[Claim] = field(default_factory=list)        # one per route no claim serves (not saved yet)
    minor_routes: list[int] = field(default_factory=list)          # for each minor claim, the index of its route
    spec_found: bool = False
    notes: list[str] = field(default_factory=list)


class _Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: int
    routes: list[int] = Field(default_factory=list)


class _RouteInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: int
    needs_auth: Optional[bool] = None
    body_fields: list[str] = Field(default_factory=list, max_length=30)
    purpose: str = Field(default="", max_length=120)


class RouteMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: list[_Link] = Field(default_factory=list)
    routes: list[_RouteInfo] = Field(default_factory=list)


def source_files_for_routes(files: Sequence[str], app_dir: str) -> list[str]:
    """The source files most likely to define routes, in the app's folder, route-looking names first."""
    prefix = f"{app_dir}/" if app_dir else ""
    pool = [f for f in files if f.startswith(prefix)]
    chosen = candidate_source_files(pool, limit=10_000)

    def rank(f: str) -> tuple[int, int, str]:
        name = PurePosixPath(f).stem.lower() + "/" + "/".join(PurePosixPath(f).parts[:-1]).lower()
        hint = 0 if any(h in name for h in _ROUTE_HINTS) else 1
        return (hint, f.count("/"), f)

    return sorted(chosen, key=rank)[:MAX_SOURCE_FILES]


def probe_spec(vm: DiscoveryVm, port: int) -> list[FoundRoute]:
    """Ask the running app for an API document in the usual places."""
    for path in SPEC_PATHS:
        res = vm.request("GET", port, path, timeout_seconds=10)
        if res.answered and res.status == 200 and res.body.lstrip()[:1] == b"{":
            routes = from_openapi(res.body)
            if routes:
                return routes
    return []


def discover(
    vm: DiscoveryVm,
    model: Optional[ChatClient],
    *,
    port: int,
    app_dir: str,
    facts: RepoFacts,
    claims: Sequence[Claim] = (),
    job_id: Optional[str] = None,
) -> Discovery:
    out = Discovery()
    spec = probe_spec(vm, port)
    out.spec_found = bool(spec)

    repo_prefix = f"{app_dir}/" if app_dir else ""
    paths = source_files_for_routes(facts.files, app_dir)
    texts = read_files(vm, paths, max_bytes=40_000) if paths else {}
    # Route prefixes are worked out relative to the app folder, so strip it from the file names for the reader.
    local = {(p[len(repo_prefix):] if p.startswith(repo_prefix) else p): t for p, t in texts.items()}
    readme = facts.text("README.md") or facts.text("readme.md") or facts.text("README")
    found = merge(spec, from_code(local), from_readme(readme))
    if not found:
        out.notes.append("no routes were found in an API document, the code or the README")
        return out

    out.routes = [Route(r.method, r.path, r.source, r.file, r.line, r.summary, list(r.body_fields), r.needs_auth) for r in found]
    testable = [c for c in claims if c.testable and c.id]
    if model is not None and testable:
        _link_with_model(out, model, testable, readme, job_id)

    linked = {i for idxs in out.links.values() for i in idxs}
    unserved = [i for i, r in enumerate(out.routes) if i not in linked and r.path.rstrip("/") not in PLUMBING and r.path not in PLUMBING]
    out.minor_routes = unserved[:MAX_MINOR_CLAIMS]
    out.minor_claims = [
        Claim(text=f"The route {out.routes[i].label()} exists and responds sensibly", claim_group="Core", importance=1,
              source="route", track="sandbox")
        for i in out.minor_routes
    ]
    return out


def _link_with_model(out: Discovery, model: ChatClient, claims: Sequence[Claim], readme: str, job_id: Optional[str]) -> None:
    shown = out.routes[:MAX_ROUTES_FOR_MODEL]
    labels = [f"{r.label()}" + (f" - {r.summary}" if r.summary else "") + (f" [{r.file}:{r.line}]" if r.file else "") for r in shown]
    try:
        mapped = ask_json(model, "test_planner", SYSTEM, build_user(labels, [c.text for c in claims], readme),
                          lambda text: parse_model(RouteMap, text), job_id=job_id, max_tokens=5000)
    except StructuredError:
        out.notes.append("the model could not link routes to claims, so every route is tested on its own")
        return
    for link in mapped.links:
        if not 1 <= link.claim <= len(claims):
            continue
        indexes = sorted({n - 1 for n in link.routes if 1 <= n <= len(shown)})
        if indexes:
            claim_id = claims[link.claim - 1].id or ""
            out.links[claim_id] = sorted(set(out.links.get(claim_id, [])) | set(indexes))
    for info in mapped.routes:
        if not 1 <= info.route <= len(shown):
            continue
        route = out.routes[info.route - 1]
        if route.needs_auth is None and info.needs_auth is not None:
            route.needs_auth = info.needs_auth
        if not route.body_fields and info.body_fields:
            route.body_fields = info.body_fields
        route.purpose = info.purpose or route.purpose


def to_json(discovery: Discovery) -> dict[str, Any]:
    """The discovery as plain data for a stage result, so the stages after it can read it."""
    return {
        "spec_found": discovery.spec_found,
        "routes": [r.__dict__ for r in discovery.routes],
        "links": discovery.links,
        "minor_claims": [c.text for c in discovery.minor_claims],
        "notes": discovery.notes,
    }


def from_json(data: dict) -> Discovery:
    d = Discovery(spec_found=bool(data.get("spec_found")), links={k: list(v) for k, v in (data.get("links") or {}).items()},
                  notes=list(data.get("notes") or []))
    d.routes = [Route(**r) for r in data.get("routes") or []]
    return d

