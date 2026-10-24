"""Stage `authorship_read` (authorship proof A3, architecture 30.5 to 30.9): from the history the Go stage `github_history` saved,
work out who wrote each claim's code and when, save one row per claim and account, and add the authorship flags.

Mostly plain code. One low-temperature model call per project looks only at the top commits that removed about as much as they
added, and says whether they were new code, moved code or reformatting. A claim that cannot be traced keeps its reason, which never
counts against anyone. Flags sit beside the score and are never subtracted from it. Running it twice replaces the rows and flags.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from talnex_ai.checks.authorship.identity import identity_of
from talnex_ai.checks.authorship.locate import NOT_REACHABLE
from talnex_ai.checks.authorship.read import (Thresholds, classify, first_person, flags_for, matching_bullet, owned_lines,
                                              parse_time, read_claim, top_commits)
from talnex_ai.checks.authorship.store import clear_flags, load_code_maps, replace_authorship, set_not_traced
from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.llm.structured import StructuredError
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import stage_result, subject_of

log = logging.getLogger("talnex.authorship")

HISTORY_NOT_AVAILABLE = "history not available"
_UNREACHABLE_HINTS = ("private", "not exist", "not found", "reach", "404", "403")


def _history_problem(history: Optional[dict]) -> Optional[str]:
    """Why the history cannot be used for any claim, or None when it can (30.9)."""
    if not history or history.get("skipped"):
        return None if history is None else f"{HISTORY_NOT_AVAILABLE} ({history.get('reason') or 'the history was not read'})"
    if not history.get("found"):
        reason = str(history.get("reason") or "")
        head = NOT_REACHABLE if any(h in reason.lower() for h in _UNREACHABLE_HINTS) else HISTORY_NOT_AVAILABLE
        return f"{head} ({reason})" if reason else head
    if int(history.get("repo_commit_count") or 0) <= 1:
        return f"{HISTORY_NOT_AVAILABLE} (the whole repository is one commit)"
    return None


def _event_start(pool, job: Job):
    if job.target_type != "project":
        return None
    with pool.connection() as conn:
        row = conn.execute("SELECT e.starts_at FROM projects p JOIN events e ON e.id = p.event_id WHERE p.id = %s::uuid",
                           (job.target_id,)).fetchone()
    return row[0] if row else None


@stage("authorship_read")
@never_stall
def authorship_read(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    history = stage_result(ctx.pool, job, "github_history")
    if history is None:
        return {"skipped": True, "reason": "the repository history was not read, so authorship was not traced"}
    claims = load_claims(ctx.pool, subject)
    maps = load_code_maps(ctx.pool, [c.id for c in claims if c.id])
    traced_ids = [cid for cid, m in maps.items() if not m["not_traced_reason"] and m["files"]]
    if not maps:
        return {"skipped": True, "reason": "no claim was mapped to code, so there is nothing to trace"}

    clear_flags(ctx.pool, subject.kind, subject.id)
    problem = _history_problem(history)
    if problem:
        for cid in traced_ids:
            set_not_traced(ctx.pool, cid, problem)
        replace_authorship(ctx.pool, list(maps), [])
        return {"skipped": True, "reason": "not traced: " + problem}

    sv = get_services(ctx.pool)
    cfg = sv.cfg.authorship
    commits = history.get("commits") or {}

    # Which top commits were moved code or reformatting: one call for the whole project, only when a commit could be one.
    owned_total: dict[str, int] = {}
    for cid in traced_ids:
        for sha, n in owned_lines(maps[cid]["files"], history.get("files") or []).items():
            owned_total[sha] = owned_total.get(sha, 0) + n
    candidates = top_commits(owned_total, commits, cfg.top_commits)
    kinds: dict[str, str] = {}
    rewrite_check = "not needed: no top commit removed about as much as it added"
    if candidates:
        try:
            kinds = classify(sv.model, candidates, job_id=job.id)
            rewrite_check = "done"
        except StructuredError as exc:
            log.warning("authorship: the new/moved/reformatting check failed: %s", exc)
            rewrite_check = "could not be done; every line is treated as new code"
    ctx.check()

    event_start = _event_start(ctx.pool, job)
    facts = stage_result(ctx.pool, job, "github_check") or {}
    fork_cutoff = parse_time(facts.get("created_at")) if history.get("is_fork") else None
    who = identity_of(ctx.pool, subject)
    # A repo owner is only a guess at the candidate's account: when it wrote nothing in the whole project it is not used for flags.
    candidate = who.candidate
    thresholds = Thresholds(cfg.one_drop_share, cfg.before_event_review, cfg.before_event_strong, cfg.claimed_min_share, cfg.reformat_share)

    by_id = {c.id: c for c in claims}
    results, out_claims = [], []
    for cid in traced_ids:
        ca = read_claim(cid, maps[cid]["files"], history, kinds, event_start=event_start, fork_cutoff=fork_cutoff)
        results.append(ca)
    if who.source == "repo_owner" and candidate and not any(ca.share_of(candidate) for ca in results):
        candidate = None

    flagged = 0
    for ca in results:
        claim = by_id[ca.claim_id]
        if ca.not_traced_reason:
            set_not_traced(ctx.pool, ca.claim_id, ca.not_traced_reason)
            out_claims.append({"claim_id": ca.claim_id, "status": "not_traced", "reason": ca.not_traced_reason})
            continue
        said = ""
        if subject.kind == "candidate_project" and claim.source == "resume":
            said = " ".join(t for t in (claim.text, matching_bullet(claim.text, who.bullets)) if t)
        findings = flags_for(claim.text, claim.importance, ca, thresholds, said_i_built=first_person(said), candidate=candidate)
        for f in findings:
            if add_flag(ctx.pool, subject.kind, subject.id, f.flag_type, f.level, f.reason, f.evidence):
                flagged += 1
        out_claims.append({
            "claim_id": ca.claim_id, "status": "traced", "total_lines": ca.total_lines, "accounts": len(ca.accounts),
            "original_repo_lines": ca.original_repo_lines, "reformatted_lines": ca.reformatted_lines, "moved_lines": ca.moved_lines,
            "before_event_share": ca.before_event_share, "flags": [f.flag_type for f in findings],
        })
    rows = replace_authorship(ctx.pool, list(maps), [ca for ca in results if not ca.not_traced_reason])
    return {"repo": history.get("repo"), "commit_sha": history.get("commit_sha"), "date_source": history.get("date_source"),
            "claims": out_claims, "rows": rows, "flags_added": flagged, "rewrite_check": rewrite_check,
            "rewrite_kinds": kinds, "ours": list(who.accounts), "ours_from": who.source,
            "candidate_account": candidate}
