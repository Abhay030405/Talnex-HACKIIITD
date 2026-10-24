"""Shared steps for reading a public coding profile page: the handle, the free Fetch, plain parsing, a model fallback.

A profile that cannot be read is "could not check": it is a result with found=false and a reason, never an error and
never a mark against the candidate. Network and budget problems are real errors and are raised so the job retries.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Mapping, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.coding.store import clear_signal, save_signal
from talnex_ai.db.jobs import Job
from talnex_ai.formats import FormatError, parse_json_block
from talnex_ai.llm.prompts import coding_profile as prompt
from talnex_ai.llm.structured import ask_json
from talnex_ai.settings import SettingsError
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import get_services

log = logging.getLogger("talnex.coding")

HANDLE_OK = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")
NOT_FOUND = re.compile(r"page not found|user (?:does not exist|not found)|no such user|profile (?:does not exist|not found)"
                       r"|doesn.t exist|\b404\b", re.I)
MAX_MODEL_TEXT = 6000


def first_number(patterns: list[str], text: str, *, as_float: bool = False) -> Optional[float]:
    """The first number captured by any of the patterns (commas allowed), or None."""
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return float(raw) if as_float else int(float(raw))
            except ValueError:
                continue
    return None


def clean(facts: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in facts.items() if v is not None}


def model_read(pool: ConnectionPool, site: str, text: str, fields: Mapping[str, str], job_id: str) -> dict[str, Any]:
    """Ask the model to copy numbers from messy text. Only whole numbers under the allowed names are kept.
    No model set, or an unusable answer, gives {} (the profile is then "could not check")."""
    try:
        answer = ask_json(
            get_services(pool).model, "claim_reader", prompt.build_system(dict(fields)),
            prompt.build_user(site, text[:MAX_MODEL_TEXT]),
            lambda t: parse_json_block(t), job_id=job_id, temperature=0.0,
        )
    except (SettingsError, FormatError) as exc:
        log.info("model fallback for %s gave nothing: %s", site, exc)
        return {}
    if not isinstance(answer, dict):
        return {}
    out: dict[str, Any] = {}
    for k in fields:
        v = answer.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            out[k] = v
    return out


def run_profile(
    job: Job, ctx: JobContext, *, site: str, signal: str, url_for: Callable[[str], str],
    parse: Callable[[str], dict[str, Any]], fields: Mapping[str, str],
) -> Mapping[str, Any]:
    """The whole candidate-level stage for one site."""
    if job.target_type != "candidate":
        raise ValueError(f"the {site} stage works on a candidate, not a {job.target_type!r}")
    with ctx.pool.connection() as conn:
        row = conn.execute("SELECT coding_handles->>%s FROM candidates WHERE id = %s::uuid", (site, job.target_id)).fetchone()
    if row is None:
        raise LookupError(f"candidate {job.target_id} does not exist")
    handle = (row[0] or "").strip()
    if not handle:
        return {"skipped": True, "reason": f"no {site} handle was given"}
    if not HANDLE_OK.match(handle):
        return {"found": False, "handle": handle[:60], "reason": f"the {site} handle has characters a profile name cannot have"}

    url = url_for(handle)
    sv = get_services(ctx.pool)
    (res,) = sv.tinyfish.fetch([url], fmt="markdown")   # free; network and budget errors are raised on purpose
    ctx.check()
    base = {"handle": handle, "profile_url": url}
    if not res.ok:
        clear_signal(ctx.pool, job.target_id, site, signal)
        why = "the profile page was not found" if res.error_code == "page_not_found" else \
            f"the profile page did not load ({res.error_code or 'unknown error'})"
        return {**base, "found": False, "reason": why}

    # A site often sends an unknown user to its home page. Numbers read from that page (a course advert saying
    # "5-star prep") are not the candidate's. The page must still be the profile, and must name the handle.
    landed = (res.final_url or url).lower()
    if handle.lower() not in landed or handle.lower() not in (res.text or "").lower():
        clear_signal(ctx.pool, job.target_id, site, signal)
        return {**base, "found": False, "reason": "the site did not show a profile for this handle (it may not exist)"}

    facts = clean(parse(res.text))
    read_by = "page text"
    if not facts:
        if NOT_FOUND.search(res.text[:800] + " " + (res.title or "")):
            clear_signal(ctx.pool, job.target_id, site, signal)
            return {**base, "found": False, "reason": "the profile page says this user does not exist"}
        facts = clean(model_read(ctx.pool, site, res.text, fields, job.id))
        read_by = "model reading of the page text"
        ctx.check()
    if not facts:
        clear_signal(ctx.pool, job.target_id, site, signal)
        return {**base, "found": False, "reason": "the profile page loaded but its numbers could not be read (layout not recognised)"}

    evidence = {**base, **facts, "read_by": read_by, "source": "public profile page"}
    save_signal(ctx.pool, job.target_id, site, signal, evidence)
    return {**base, "found": True, "read_by": read_by, "facts": facts}
