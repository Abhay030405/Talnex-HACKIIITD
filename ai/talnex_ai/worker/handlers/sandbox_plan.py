"""Stage `sandbox_plan` (R5 of the sandbox track, architecture 28.7): write the backend tests.

Works for a hackathon project and a project on a resume alike. It needs the routes `route_discovery` saved with the run.

  claims a route serves     the model writes HTTP plans (normal use, a known answer, a repeat) from the real routes
  route-exists claims       a plan built by code: the route answers without a server error
  Setup, Edge cases, Access, Reliability claims of TalNex's own, with plans built by code (sandbox/api_tests/derive.py)

The plans are saved in this stage's result, the way `test_plan` saves the live ones, and `sandbox_test` runs them.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Optional

from talnex_ai.claims.store import load_claims, save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim
from talnex_ai.sandbox.api_tests.derive import AUTH_TEXT, auth_routes, derive
from talnex_ai.sandbox.api_tests.plan import HttpPlan, smoke_plan
from talnex_ai.sandbox.api_tests.planner import plan_claim_http
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.route_discovery import Route, from_json
from talnex_ai.sandbox.stack_detect.gather import read_files
from talnex_ai.sandbox.store import latest_run
from talnex_ai.scoring.talnex_score.checklist import write_checklist
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, set_status, subject_of

log = logging.getLogger("talnex.sandbox_plan")

SNIPPET_BEFORE, SNIPPET_AFTER = 3, 18
MAX_SNIPPET_FILES = 4
MAX_SNIPPET_CHARS = 5000


def route_snippets(vm, routes: list[Route], app_dir: str) -> dict[str, str]:
    """The few lines of code around each given route, so the planner knows the fields and checks a route really uses."""
    wanted = [r for r in routes if r.file and r.line][:MAX_SNIPPET_FILES * 2]
    paths = sorted({f"{app_dir}/{r.file}" if app_dir else r.file for r in wanted})[:MAX_SNIPPET_FILES]
    if not paths:
        return {}
    try:
        texts = read_files(vm, paths, max_bytes=60_000)
    except SandboxError:
        return {}
    out: dict[str, str] = {}
    budget = MAX_SNIPPET_CHARS
    for r in wanted:
        text = texts.get(f"{app_dir}/{r.file}" if app_dir else r.file)
        if not text or budget <= 0:
            continue
        lines = text.splitlines()
        piece = "\n".join(lines[max(0, r.line - 1 - SNIPPET_BEFORE): r.line + SNIPPET_AFTER])[:1500]
        out[f"{r.label()} ({r.file}:{r.line})"] = piece
        budget -= len(piece)
    return out




@stage("sandbox_plan")
@never_stall
def sandbox_plan(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    run = latest_run(ctx.pool, subject)
    if run is None or run.status != "running" or not run.vm_id:
        return {"skipped": True, "reason": "the app is not running, so there are no backend tests to plan"}
    data = run.resources.get("discovery")
    if not data or not data.get("routes"):
        return {"skipped": True, "reason": "no routes were found, so there is nothing to test over HTTP"}
    discovery = from_json(data)
    routes = discovery.routes
    set_status(ctx.pool, info, "testing")

    # Which routes serve a claim (route indexes), by claim id, as route discovery linked them.
    served = {i for idxs in discovery.links.values() for i in idxs}
    derived = derive(routes, served)
    saved = {c.text: c for c in save_claims(ctx.pool, subject, derived.claims)}

    plans: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    readme = ""
    vm = sv.sandbox.attach(run.vm_id)
    app_dir = run.resources.get("app_dir") or ""

    for text, plan in derived.plans.items():
        claim = saved.get(text)
        if claim and claim.id:
            plans[claim.id] = {"plans": [plan.model_dump(mode="json")]}

    # A sign-in test, when the app has sign-in routes: it proves signing in works and gives the other tests a token to use.
    auth_found = auth_routes(routes)
    if auth_found and sv.model is not None:
        (auth_claim,) = save_claims(ctx.pool, subject, [Claim(text=AUTH_TEXT, claim_group="Access", importance=2, source="route", track="sandbox")])
        try:
            written = plan_claim_http(sv.model, auth_claim, routes, snippets=route_snippets(vm, auth_found, app_dir), only="normal", job_id=job.id)
            if written and auth_claim.id:
                plans[auth_claim.id] = {"plans": [p.model_dump(mode="json") for p in written]}
        except Exception as exc:  # no sign-in plan: the other tests simply run without a token
            log.warning("no sign-in plan: %s", exc)
            errors[auth_claim.id or ""] = f"no test could be written for signing in ({type(exc).__name__})"

    by_id = {c.id: c for c in load_claims(ctx.pool, subject, testable_only=True) if c.id}
    for claim_id, indexes in discovery.links.items():
        claim = by_id.get(claim_id)
        if claim is None or claim_id in plans:
            continue
        mine = [routes[i] for i in indexes if i < len(routes)]
        if claim.source == "route":
            # "The route X exists and responds sensibly": built by code, no model.
            r = mine[0] if mine else None
            built = smoke_plan(r.method, r.path, r.body_fields) if r else None
            if built is None:
                errors[claim_id] = "a route that deletes is not tried: the test cannot know what it would remove"
            else:
                plans[claim_id] = {"plans": [built.model_dump(mode="json")]}
            continue
        try:
            written = plan_claim_http(sv.model, claim, routes, snippets=route_snippets(vm, mine, app_dir), readme=readme, job_id=job.id)
        except Exception as exc:  # no plan could be written: the claim is left untested, never marked broken
            log.warning("no HTTP plan for claim %s: %s", claim_id, exc)
            errors[claim_id] = f"no test could be written for this claim ({type(exc).__name__})"
            continue
        if written:
            plans[claim_id] = {"plans": [p.model_dump(mode="json") for p in written]}

    # The scoring checklist for every backend claim is written NOW, before any test has run (the score later rests on a list
    # made without seeing the results). The items describe what the API does, so they are written in "from code" mode.
    everyone = [by_id[i] if i in by_id else next((c for c in saved.values() if c.id == i), None) for i in list(plans)]
    everyone += [c for c in saved.values() if c.id not in plans]          # the Setup claim has no requests but is scored too
    wanted = [c for c in everyone if c is not None and c.id]

    def checklist_for(claim: Claim):
        try:
            return claim.id, {"checklist": write_checklist(sv.model, claim.text, claim.claim_group, info.role_level,
                                                           job_id=job.id, from_code=True).model_dump()}
        except Exception as exc:   # a claim without a checklist is still tested; its score is written from the evidence later
            log.warning("no checklist for claim %s: %s", claim.id, exc)
            return claim.id, None

    checklists: dict[str, Any] = {}
    if sv.model is not None and wanted:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for claim_id, entry in pool.map(checklist_for, wanted):
                if entry:
                    checklists[claim_id] = entry
    return {"claims": plans, "checklists": checklists, "errors": errors, "derived": [c.text for c in derived.claims], "routes": len(routes)}
