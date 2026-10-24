"""Run an HTTP plan against the app in a VM and keep the proof (architecture 28.7 and 28.12).

Every step is sent from inside the VM, its answer is checked by plain code against what the plan expects, and the request and
the answer are saved as a record under `sandbox/{project}/{run}/step-N.json` so a reader can replay it by hand. The run ends in
the same shape as a live run (a RunRecord), so the never-blame ladder, the verdict rules and the scoring do not care which
runner produced it.

  works         every step that could be judged passed
  partly_works  some passed and some failed
  broken        none passed and at least one failed
  blocked       nothing could be judged (the app did not answer, or every answer was a "soft" one such as a sign-in wall)
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from psycopg_pool import ConnectionPool

from talnex_ai.formats import Claim, StepRecord
from talnex_ai.safety.site_rules import LimitReached, next_try_number, tries_used_for_claim
from talnex_ai.sandbox.api_tests.plan import HttpPlan, HttpStep
from talnex_ai.sandbox.client import HttpResult
from talnex_ai.storage.keys import sandbox_key
from talnex_ai.testing.runner import store
from talnex_ai.testing.runner.runner import RunRecord

log = logging.getLogger("talnex.api_tests")

BODY_KEPT = 6000          # characters of an answer kept in a proof record
REQUEST_TIMEOUT = 20
_VAR = re.compile(r"\{([A-Za-z_]\w*)\}")
_DB_OUTCOME = {"works": "passed", "partly_works": "passed", "broken": "failed", "blocked": "blocked"}


class ApiVm(Protocol):
    def request(self, method: str, port: int, path: str, **kwargs) -> HttpResult: ...


class FileSink(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str = ...) -> None: ...


@dataclass
class StepVerdict:
    status: str                  # pass / fail / unconfirmed
    why: str
    results: list[HttpResult] = field(default_factory=list)


def fill(value: Any, variables: dict[str, str]) -> Any:
    """Put captured values into {name} places of a path, header or body. Raises KeyError for a value not captured."""
    if isinstance(value, str):
        return _VAR.sub(lambda m: variables[m.group(1)], value)
    if isinstance(value, list):
        return [fill(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, variables) for k, v in value.items()}
    return value


def dig(data: Any, dotted: str) -> Optional[str]:
    """A value from parsed JSON by a dotted path ("data.items.0.id"), as text, or None. Several places may be given with | and the
    first one that has a value wins ("id|_id|data.id")."""
    if "|" in dotted:
        return next((v for v in (dig(data, one) for one in dotted.split("|")) if v is not None), None)
    node = data
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return None if node is None or isinstance(node, (dict, list)) else str(node)


def expectation_text(step: HttpStep) -> str:
    if step.expect_status:
        text = "status " + " or ".join(str(s) for s in step.expect_status)
    elif step.expect_below:
        text = f"an answer below {step.expect_below} (no server error)" if step.expect_below == 500 else f"a status below {step.expect_below}"
    else:
        text = "a 2xx answer"
    if step.expect_contains:
        text += "; the body contains " + ", ".join(repr(c) for c in step.expect_contains)
    if step.expect_json_keys:
        text += "; the JSON has " + ", ".join(step.expect_json_keys)
    return text


# Keys that carry a sign-in token. An app that keeps the session in a cookie has none of them in its sign-in answer.
TOKEN_KEYS = {"token", "access_token", "accesstoken", "auth_token", "authtoken", "id_token", "idtoken", "jwt", "session", "session_id", "sessionid"}


def _sets_cookie(res: HttpResult) -> bool:
    return any(k.lower() == "set-cookie" and v for k, v in res.headers.items())


def judge_answer(step: HttpStep, res: HttpResult) -> tuple[str, str]:
    """('pass' | 'fail' | 'unconfirmed', why) for one answer."""
    if not res.answered:
        error = res.error or "no answer"
        if "did not answer in time" in error and step.parallel > 1:
            return "unconfirmed", "one of the requests timed out, which can be the test machine being slow"
        return "fail", f"no answer: {error}"
    status = res.status
    if status in step.soft_status:
        return "unconfirmed", f"status {status}, which means the request did not reach what we wanted to test"
    if step.expect_status:
        ok = status in step.expect_status
    elif step.expect_below:
        ok = status < step.expect_below
    else:
        ok = 200 <= status < 300
    if not ok:
        return "fail", f"status {status}; expected {expectation_text(step)}"
    body = res.text
    for needle in step.expect_contains:
        if needle.lower() not in body.lower():
            return "fail", f"status {status}, but the body does not contain {needle!r}"
    if step.expect_json_keys:
        try:
            data = res.json()
        except ValueError:
            return "fail", f"status {status}, but the body is not JSON"
        node = data[0] if isinstance(data, list) and data else data
        missing = [k for k in step.expect_json_keys if not (isinstance(node, dict) and k in node)]
        if _sets_cookie(res):
            # The session came back as a cookie (the next steps send it), so a missing token key is not a failure.
            missing = [k for k in missing if k.lower() not in TOKEN_KEYS]
        if missing:
            return "fail", f"status {status}, but the JSON lacks {', '.join(missing)}"
    return "pass", f"status {status}"


def remember_cookies(jar: dict[str, str], results: list[HttpResult]) -> None:
    """Keep the cookies an answer sets, the way a browser does: a new value replaces the old one, an empty value or a
    Max-Age of 0 removes it. Only the name and value are kept (the path and flags do not matter for a test)."""
    for res in results:
        sent = next((v for k, v in res.headers.items() if k.lower() == "set-cookie"), [])
        for line in sent:
            parts = [p.strip() for p in line.split(";")]
            name, _, value = parts[0].partition("=")
            if not name:
                continue
            expired = any(p.lower().replace(" ", "") == "max-age=0" for p in parts[1:])
            if value == "" or expired:
                jar.pop(name, None)
            else:
                jar[name] = value


def _send(vm: ApiVm, port: int, step: HttpStep, variables: dict[str, str],
          default_headers: Optional[dict[str, str]] = None, jar: Optional[dict[str, str]] = None) -> tuple[dict, list[HttpResult]]:
    path = fill(step.path, variables)
    own: dict[str, str] = {}
    for name, value in step.headers.items():
        try:
            own[str(name)] = str(fill(value, variables))
        except KeyError:
            # A header built from a value that was never captured (a sign-in token) is left out when the app set a cookie session:
            # the cookie is what signs the request in. Without a cookie the step is unconfirmed, as before.
            if not jar:
                raise
    # The sign-in token is added to every request that did not ask to go without it, unless the step sets that header itself.
    inherited = {} if step.anonymous else {k: v for k, v in (default_headers or {}).items() if k.lower() not in {h.lower() for h in own}}
    if step.basic_auth:
        who = fill(step.basic_auth, variables)
        own["Authorization"] = "Basic " + base64.b64encode(f"{who['username']}:{who['password']}".encode()).decode()
        inherited.pop("Authorization", None)
    headers = {**inherited, **own}
    # Cookies the app set earlier go along, as a browser would send them (a step that goes without sign-in sends none).
    if jar and not step.anonymous and "cookie" not in {h.lower() for h in headers}:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
    body: Optional[bytes] = None
    if step.json_body is not None:
        body = json.dumps(fill(step.json_body, variables)).encode()
        headers.setdefault("Content-Type", "application/json")
    elif step.raw_body is not None:
        body = fill(step.raw_body, variables).encode()
    shown_headers = {k: ("***" if k.lower() in ("authorization", "cookie") else v) for k, v in headers.items()}
    request = {"method": step.method, "path": path, "headers": shown_headers, "body": body.decode("utf-8", "replace")[:BODY_KEPT] if body else None}

    def once(_: int) -> HttpResult:
        return vm.request(step.method, port, path, headers=headers, body=body, timeout_seconds=REQUEST_TIMEOUT)

    if step.parallel > 1:
        with ThreadPoolExecutor(max_workers=step.parallel) as pool:
            results = list(pool.map(once, range(step.parallel)))
    else:
        results = [once(0)]
    return request, results


def _with_values(step: HttpStep, variables: dict[str, str]) -> HttpStep:
    """The step with the captured values put into what it expects, so "the body contains talnex-{run}" checks the real value."""
    try:
        return step.model_copy(update={"expect_contains": [fill(c, variables) for c in step.expect_contains]})
    except KeyError:
        return step


def _verdict(step: HttpStep, results: list[HttpResult]) -> StepVerdict:
    judged = [judge_answer(step, r) for r in results]
    fails = [w for s, w in judged if s == "fail"]
    soft = [w for s, w in judged if s == "unconfirmed"]
    if fails:
        why = fails[0] if len(results) == 1 else f"{len(fails)} of {len(results)} requests failed: {fails[0]}"
        return StepVerdict("fail", why, results)
    if soft and len(soft) == len(results):
        return StepVerdict("unconfirmed", soft[0], results)
    ok = [w for s, w in judged if s == "pass"]
    why = ok[0] if len(results) == 1 else f"{len(ok)} of {len(results)} requests passed ({ok[0]})"
    return StepVerdict("pass", why, results)


def _record(step: HttpStep, request: dict, verdict: StepVerdict) -> dict:
    return {
        "request": request, "parallel": step.parallel, "expected": expectation_text(step),
        "responses": [
            {"status": r.status, "error": r.error, "duration_ms": r.duration_ms, "headers": {k: v[0] for k, v in list(r.headers.items())[:12]},
             "body": r.text[:BODY_KEPT], "truncated": r.truncated or len(r.text) > BODY_KEPT}
            for r in verdict.results[:3]
        ],
        "judged": {"status": verdict.status, "why": verdict.why},
    }


def execute(vm: ApiVm, port: int, plan: HttpPlan, save: Optional[Any] = None, *, default_headers: Optional[dict[str, str]] = None,
            variables_out: Optional[dict[str, str]] = None,
            cookies_out: Optional[dict[str, str]] = None) -> tuple[str, str, list[StepRecord], Optional[str]]:
    """Run every step. `save(step_number, record_dict) -> proof key or None`. Returns (outcome, observed, steps, stop_reason).
    `default_headers` (a sign-in token) go on every step that is not anonymous. Values captured along the way are copied to `variables_out`.
    Cookies the app sets are sent back on later steps that are not anonymous and are left in `cookies_out` (a cookie session)."""
    variables: dict[str, str] = variables_out if variables_out is not None else {}
    jar: dict[str, str] = cookies_out if cookies_out is not None else {}
    # {run} is a fresh short value for every execution of a plan. Plans put it in emails and usernames so a sign-up never collides
    # with one an earlier plan (or an earlier try of this one) already made.
    variables.setdefault("run", uuid.uuid4().hex[:8])
    records: list[StepRecord] = []
    counts = {"pass": 0, "fail": 0, "unconfirmed": 0}
    first_unreachable = False
    notes: list[str] = []
    for number, step in enumerate(plan.steps, start=1):
        started = time.monotonic()
        try:
            request, results = _send(vm, port, step, variables, default_headers, jar)
            if not step.anonymous:
                remember_cookies(jar, results)
            verdict = _verdict(_with_values(step, variables), results)
        except KeyError as exc:
            # A value an earlier step should have captured is missing: that step already failed or was unconfirmed.
            request = {"method": step.method, "path": step.path, "headers": {}, "body": None}
            verdict = StepVerdict("unconfirmed", f"needs {exc} from an earlier step, which did not give it")
        counts[verdict.status] += 1
        if number == 1 and verdict.status == "fail" and verdict.results and not any(r.answered for r in verdict.results):
            first_unreachable = True
        if verdict.status == "pass" and step.capture and verdict.results and verdict.results[0].answered:
            try:
                data = verdict.results[0].json()
                for name, dotted in step.capture.items():
                    value = dig(data, dotted)
                    if value is not None:
                        variables[name] = value
            except ValueError:
                pass
        key = save(number, _record(step, request, verdict)) if save else None
        action = f"{step.method} {fill_safe(step.path, variables)}" + (f" ({step.note})" if step.note else "")
        records.append(StepRecord(
            step_number=number, kind="http", action=action[:300], expected=expectation_text(step),
            observed=f"{verdict.status}: {verdict.why}"[:500], proof_key=key, duration_ms=int((time.monotonic() - started) * 1000)))
        notes.append(f"{number}. {verdict.status}")
        if first_unreachable:
            break

    if first_unreachable:
        return "blocked", "the app did not answer the very first request", records, "the app was not answering"
    if counts["fail"] == 0 and counts["pass"] == 0:
        return "blocked", "no step could be judged: " + records[0].observed, records, "nothing could be confirmed"
    observed = f"{counts['pass']} passed, {counts['fail']} failed, {counts['unconfirmed']} could not be confirmed"
    if counts["fail"] == 0:
        return "works", observed, records, None
    if counts["pass"] > 0:
        failed = next(r.observed for r in records if r.observed and r.observed.startswith("fail"))
        return "partly_works", f"{observed}; first failure: {failed}", records, None
    failed = next(r.observed for r in records if r.observed and r.observed.startswith("fail"))
    return "broken", f"{observed}; first failure: {failed}", records, None


def fill_safe(path: str, variables: dict[str, str]) -> str:
    try:
        return fill(path, variables)
    except KeyError:
        return path


def run_http_plan(
    *,
    pool: ConnectionPool,
    files: FileSink,
    vm: ApiVm,
    port: int,
    claim: Claim,
    plan: HttpPlan,
    subject_id: str,
    max_tries_per_claim: int,
    default_headers: Optional[dict[str, str]] = None,
    variables_out: Optional[dict[str, str]] = None,
    cookies_out: Optional[dict[str, str]] = None,
) -> RunRecord:
    """Run one plan for one claim and save the run, its steps and their proof. Raises LimitReached when the claim has used
    all its tries (nothing is created then). A problem on our side ends the run as blocked, never as broken."""
    if claim.id is None:
        raise ValueError("the claim must be saved before it can be tested")
    used = tries_used_for_claim(pool, claim.id)
    if used >= max_tries_per_claim:
        raise LimitReached(f"already tried this claim {used} times (limit {max_tries_per_claim})")
    try_number = next_try_number(pool, claim.id) or 1
    run_id = store.create_run(pool, claim.id, try_number, plan.test_type, track="sandbox", method="http")

    def save(number: int, record: dict) -> Optional[str]:
        key = sandbox_key(subject_id, run_id, f"step-{number}.json")
        try:
            files.put_bytes(key, json.dumps(record, indent=1).encode("utf-8"), "application/json")
            return key
        except Exception as exc:  # the step is still recorded, just without its file
            log.warning("could not save proof %s: %s", key, exc)
            return None

    outcome, observed, steps, stop = "blocked", "", [], None
    db_outcome = "error"
    try:
        outcome, observed, steps, stop = execute(vm, port, plan, save, default_headers=default_headers, variables_out=variables_out,
                                                 cookies_out=cookies_out)
        db_outcome = _DB_OUTCOME[outcome]
    except Exception as exc:
        log.exception("http run %s crashed", run_id)
        observed = stop = f"the test run hit a problem on our side: {type(exc).__name__}"
    finally:
        try:
            store.add_steps(pool, run_id, steps)
            store.finish_run(pool, run_id, db_outcome)
        except Exception:
            log.exception("could not save run %s", run_id)
    return RunRecord(run_id, try_number, outcome, observed, steps, stop, None, None, False)  # type: ignore[arg-type]
