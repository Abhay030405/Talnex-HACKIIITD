"""Claims and plans that come from the routes themselves, not from anything the team wrote (architecture 28.7 and 28.11).

A backend project is judged by how well its routes behave, so besides the claims it makes, TalNex adds claims of its own,
each in the scoring group the architecture assigns to its kind of test:

  Setup        the project builds and starts from its instructions
  Edge cases   a route that takes input answers bad input without crashing
  Access       routes that look protected turn away a missing or a wrong token
  Reliability  the app survives ten requests at once

Everything here is pure: routes in, claims and plans out. Names follow the route list so the same routes always give the same
claims, which makes re-running a project safe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from talnex_ai.formats import Claim
from talnex_ai.sandbox.api_tests.plan import HttpPlan, WRITE_METHODS, access_plan, collection_path, edge_plan, has_params, load_plan
from talnex_ai.sandbox.route_discovery import PLUMBING, Route

MAX_EDGE_CLAIMS = 8
SETUP_TEXT = "The project builds and starts from its instructions"
ACCESS_TEXT = "Routes that need a sign-in turn away requests with no token or a wrong token"
LOAD_TEXT = "The app answers ten requests at the same time without crashing"
AUTH_TEXT = "A user can sign up, sign in, and use the token on a route that needs it"
_AUTH_PATH = re.compile(r"(login|log-in|signin|sign-in|signup|sign-up|register|token|auth|session)", re.IGNORECASE)
_VAR = re.compile(r"\{([A-Za-z_]\w*)\}")


@dataclass
class Derived:
    claims: list[Claim] = field(default_factory=list)
    plans: dict[str, HttpPlan] = field(default_factory=dict)      # claim text -> its plan (Setup has none)


def _claim(text: str, group: str, importance: int, source: str = "route") -> Claim:
    return Claim(text=text, claim_group=group, importance=importance, source=source, track="sandbox")  # type: ignore[arg-type]


def edge_claim_text(r: Route) -> str:
    return f"{r.method} {r.path} answers bad input without crashing"


def derive(routes: Sequence[Route], served: Optional[set[int]] = None) -> Derived:
    """The extra claims and their plans. `served` are the indexes of routes some claim already uses (they are tested first)."""
    served = served or set()
    out = Derived()
    out.claims.append(_claim(SETUP_TEXT, "Setup", 2, source="readme"))

    # Edge cases: routes that take input (a body or an id), those serving a claim and those with known fields first.
    candidates = [(i, r) for i, r in enumerate(routes) if (r.method in WRITE_METHODS or has_params(r.path)) and r.method != "DELETE"]
    candidates.sort(key=lambda t: (t[0] not in served, not t[1].body_fields, t[0]))
    seen: set[str] = set()
    for _, r in candidates:
        text = edge_claim_text(r)
        source = None
        if has_params(r.path):
            parent = collection_path(r.path)
            maker = next((x for x in routes if x.method == "POST" and x.path.rstrip("/") == parent.rstrip("/") and not has_params(x.path)), None)
            source = (maker.path, maker.body_fields) if maker else None
        plan = edge_plan(r.method, r.path, r.body_fields, r.needs_auth, source)
        if plan is None or text in seen:
            continue
        seen.add(text)
        out.claims.append(_claim(text, "Edge cases", 2))
        out.plans[text] = plan
        if len(seen) == MAX_EDGE_CLAIMS:
            break

    protected = [(r.method, r.path, r.body_fields) for r in routes if r.needs_auth and r.method != "DELETE"]
    plan = access_plan(protected)
    if plan is not None:
        out.claims.append(_claim(ACCESS_TEXT, "Access", 2))
        out.plans[ACCESS_TEXT] = plan

    load_path = next((r.path for r in routes if r.method in ("GET", "ANY") and not has_params(r.path) and not r.needs_auth), None)
    if load_path is not None:
        out.claims.append(_claim(LOAD_TEXT, "Reliability", 1))
        out.plans[LOAD_TEXT] = load_plan(load_path)
    return out


def auth_routes(routes: Sequence[Route]) -> list[Route]:
    """The routes that look like signing up or in. Their presence is what makes a sign-in test worth writing."""
    return [r for r in routes if r.method in ("POST", "PUT", "GET", "ANY") and _AUTH_PATH.search(r.path)]


def auth_header_from(plan: HttpPlan, captured: Mapping[str, str]) -> dict[str, str]:
    """The header a successful sign-in run proved works: the first step header that used a captured value, with the value put in.
    e.g. {"Authorization": "Bearer abc123"}. Empty when the plan used no captured value in a header."""
    for step in plan.steps:
        for name, value in step.headers.items():
            names = _VAR.findall(value)
            if names and all(n in captured for n in names):
                return {name: _VAR.sub(lambda m: captured[m.group(1)], value)}
    return {}


def session_header_from(plan: HttpPlan, captured: Mapping[str, str], cookies: Mapping[str, str]) -> dict[str, str]:
    """What every later test sends to be signed in: the header with the captured token when the plan used one, else the
    session cookies the app set (a cookie session has no token in the answer). Empty when neither exists."""
    header = auth_header_from(plan, captured)
    if header or not cookies:
        return header
    return {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}


def is_plumbing(path: str) -> bool:
    return path.rstrip("/") in PLUMBING or path in PLUMBING
