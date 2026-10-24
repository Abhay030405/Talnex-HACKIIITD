"""The backend test planner: a claim and the routes that serve it become HTTP plans (architecture 28.7).

Plain code decides which kinds of test apply and checks every plan the model writes: each path must be a real route, nothing
may delete what the plan did not create, and an expected result must describe the claim being TRUE (a hedged one passes
whatever happens). The model only writes the requests."""
from __future__ import annotations

import re
from typing import Optional, Sequence

from talnex_ai.formats import Claim, FormatError, TestType, parse_list
from talnex_ai.llm.prompts.http_test_planner import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.sandbox.api_tests.plan import HttpPlan
from talnex_ai.sandbox.route_discovery import Route
from talnex_ai.sandbox.route_discovery.extract import normalise_path
from talnex_ai.testing.planner.planner import hedge

MODEL_TYPES: tuple[TestType, ...] = ("normal", "known_answer", "repeat")
_COMPUTES = re.compile(
    r"\b(calculat|convert|total|sum|average|count|translat|summari[sz]|analy[sz]|score|predict|search|filter|sort|rank|recommend|"
    r"classif|detect|extract|generat|validate|parse|format)", re.IGNORECASE)
_VAR = re.compile(r"\{[A-Za-z_]\w*\}")
_NUMBER = re.compile(r"/\d+(?=/|$)")


def applicable_types(claim: Claim) -> list[TestType]:
    if not claim.testable:
        return []
    types: list[TestType] = ["normal"]
    if _COMPUTES.search(claim.text):
        types.append("known_answer")
    if claim.importance == 3:
        types.append("repeat")
    return types


def route_line(r: Route) -> str:
    extra = []
    if r.body_fields:
        extra.append("body fields: " + ", ".join(r.body_fields))
    if r.needs_auth:
        extra.append("needs a sign-in token")
    if r.purpose or r.summary:
        extra.append(r.purpose or r.summary)
    return f"{r.method} {r.path}" + (f"  ({'; '.join(extra)})" if extra else "")


def _shape(path: str) -> str:
    """A path with every changing part written the same way, so /items/7, /items/{id} and /items/:id all compare equal."""
    path = path.split("?")[0]
    path = _VAR.sub("{}", path)
    path = _NUMBER.sub("/{}", path)
    return normalise_path(path)


def _known(routes: Sequence[Route]) -> list[tuple[str, list[str]]]:
    """(method, path pieces) of every route, with each parameter piece written {} so any real value fits it."""
    return [(("*" if r.method == "ANY" else r.method), _shape(r.path).strip("/").split("/")) for r in routes]


def _is_known(method: str, path: str, known: list[tuple[str, list[str]]]) -> bool:
    pieces = _shape(path).strip("/").split("/")
    for m, route in known:
        if m not in (method, "*") or len(route) != len(pieces):
            continue
        if all(r == "{}" or r == p or p == "{}" for r, p in zip(route, pieces)):
            return True
    return False


def check_plans(plans: list[HttpPlan], wanted: Sequence[TestType], routes: Sequence[Route]) -> list[HttpPlan]:
    """Raises FormatError (so the model gets one repair try) when the plans do not fit what was asked or use unknown routes."""
    got = [p.test_type for p in plans]
    missing = [t for t in wanted if t not in got]
    if missing:
        raise FormatError(f"no plan was given for test type(s): {', '.join(missing)}")
    plans = [p for p in plans if p.test_type in wanted]
    known = _known(routes)
    seen: set[str] = set()
    for plan in plans:
        if plan.test_type in seen:
            raise FormatError(f"more than one plan for test type {plan.test_type}; write exactly one each")
        seen.add(plan.test_type)
        vague = hedge(plan.expected_result) or hedge(plan.steps[-1].note or "")
        if vague:
            raise FormatError(f'the expected result says "{vague}", which would pass whatever happens. State the claim being TRUE as one concrete thing the answers show.')
        for step in plan.steps:
            if not _is_known(step.method, step.path, known):
                raise FormatError(f"{step.method} {step.path} is not one of the listed routes; use only the routes you were given")
    return plans


def plan_claim_http(
    client: ChatClient,
    claim: Claim,
    routes: Sequence[Route],
    *,
    snippets: Optional[dict[str, str]] = None,
    readme: str = "",
    avoid: Optional[HttpPlan] = None,
    only: Optional[TestType] = None,
    job_id: Optional[str] = None,
) -> list[HttpPlan]:
    """Plans for one claim. `routes` are all the routes of the app (the plan may need sign-up and sign-in routes too).
    `avoid`: a plan that did not work out; the new plan tests the same thing another way. `only`: write just this one kind."""
    wanted = applicable_types(claim)
    if only is not None:
        wanted = [only] if wanted else []
    wanted = [t for t in wanted if t in MODEL_TYPES]
    if not wanted:
        return []

    def parse(answer: str) -> list[HttpPlan]:
        return check_plans(parse_list(HttpPlan, answer, key="plans"), wanted, routes)

    plans = ask_json(
        client, "test_planner", SYSTEM,
        build_user(claim.text, wanted, [route_line(r) for r in routes], snippets=snippets, readme=readme,
                   avoid=[f"{s.method} {s.path} ({s.note})" for s in avoid.steps] if avoid else None),
        parse, job_id=job_id, max_tokens=6000,
    )
    order = {t: i for i, t in enumerate(wanted)}
    return sorted((p.model_copy(update={"claim_id": claim.id}) for p in plans), key=lambda p: order[p.test_type])
