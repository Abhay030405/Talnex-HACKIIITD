"""Stage `code_locate` (authorship proof A1, architecture 30.3): map every claim of a project to the files and line ranges that make
the feature work, so the Go stage `github_history` can read who wrote those lines.

Runs after `github_check` and `route_discovery`, for a hackathon project and a resume project alike, for every claim with a repo,
tested or not. The code is read with free TinyFish Fetch calls on the repo's raw files. A claim whose code is not found with enough
confidence is saved as "could not trace" with the reason; that never counts against anyone. Running it twice replaces the rows.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping
from urllib.parse import quote

from talnex_ai.checks.authorship.locate import NOT_REACHABLE, CodeMap, locate
from talnex_ai.checks.authorship.store import save_code_maps
from talnex_ai.claims.store import load_claims
from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.store import latest_run
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, stage_result, subject_of

log = logging.getLogger("talnex.code_locate")

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def _raw(repo: str, branch: str, path: str) -> str:
    return RAW.format(repo=repo, branch=quote(branch, safe=""), path=quote(path))


@stage("code_locate")
@never_stall
def code_locate(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    if not info.repo_url:
        return {"skipped": True, "reason": "there is no repository link, so no code could be traced"}
    claims = load_claims(ctx.pool, subject)
    if not claims:
        return {"skipped": True, "reason": "there are no claims to trace"}

    facts = stage_result(ctx.pool, job, "github_check") or {}
    if not facts.get("found"):
        why = f"{NOT_REACHABLE} ({facts.get('reason') or 'the repository could not be read'})"
        save_code_maps(ctx.pool, [CodeMap(c.id or "", not_traced_reason=why) for c in claims if c.id])
        return {"skipped": True, "reason": "not traced: " + why}

    sv = get_services(ctx.pool)
    cfg = sv.cfg.authorship
    repo, branch = facts["repo"], facts.get("default_branch") or "main"

    def read(paths: list[str]) -> dict[str, str]:
        urls = [_raw(repo, branch, p) for p in paths]
        # "html" returns a plain file exactly as written; "markdown" would rewrite code (it escapes underscores).
        by_url = {r.url: r for r in sv.tinyfish.fetch(urls, fmt="html")} if urls else {}
        return {p: by_url[u].text for p, u in zip(paths, urls) if by_url.get(u) is not None and by_url[u].ok}

    run = latest_run(ctx.pool, subject)
    resources = run.resources if run is not None else {}
    maps = locate(
        claims, files=facts.get("files") or [], read=read, model=sv.model,
        locate_max_files=cfg.locate_max_files, max_repo_files=cfg.max_repo_files, max_claims=cfg.max_claims,
        max_files_per_claim=cfg.max_files_per_claim, min_confidence=cfg.min_confidence,
        discovery=resources.get("discovery") or {}, app_dir=resources.get("app_dir") or "",
        files_truncated=bool(facts.get("files_truncated")), job_id=job.id, check=ctx.check,
    )
    save_code_maps(ctx.pool, maps)
    return {"repo": repo, "branch": branch, "commit_sha": None, "claims": [m.as_json() for m in maps]}
