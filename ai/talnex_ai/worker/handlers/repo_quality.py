"""Stage `repo_quality` (recruiter and hackathon, one per project): the submitted repository judged as engineering work.

Reads the repo through GitHub's official API (the file tree, a few key files, recent commits), runs the plain-code
checks in checks/repo_quality, asks the model only for consistency and error handling, and saves one row per area in
`repo_quality`. Evidence beside the score: it never changes a feature score. Safe to run twice (rows are replaced).
A repo GitHub will not show (private, rate limit, missing) ends as skipped with the reason, never as a failure.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping, Optional

import httpx
from pydantic import BaseModel, Field

from talnex_ai.checks import repo_quality as rq
from talnex_ai.db.jobs import Job
from talnex_ai.formats import FormatError, parse_model
from talnex_ai.llm.prompts import repo_quality as prompt
from talnex_ai.llm.structured import ask_json
from talnex_ai.reports.ask_tools import GitHubReader, ToolRefused, repo_of
from talnex_ai.sandbox.store import latest_run
from talnex_ai.settings import SettingsError
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, subject_of

log = logging.getLogger("talnex.repo_quality")


class _Evidence(BaseModel):
    path: str
    note: str = ""


class _Judgement(BaseModel):
    score: float = Field(ge=0, le=10)
    summary: str = Field(min_length=1, max_length=600)
    evidence: list[_Evidence] = Field(default_factory=list)


def read_facts(gh: GitHubReader, repo: str, cfg, sandbox: Optional[Mapping[str, Any]]) -> rq.RepoFacts:
    """Everything the checks need, within the read limits."""
    paths, sizes, _branch = gh.tree(repo)
    files: dict[str, str] = {}
    budget = cfg.max_bytes
    for path in rq.pick_files(paths, sizes, cfg.max_files):
        if budget <= 0:
            break
        try:
            text = gh.file(repo, path)
        except ToolRefused:
            continue
        files[path] = text
        budget -= len(text)
    readme = next((p for p in paths if re.match(r"(?i)^readme(\.[a-z]+)?$", p)), None)
    try:
        branches = gh.branch_count(repo)
    except ToolRefused:
        branches = 1
    return rq.RepoFacts(paths=paths, sizes=sizes, files=files, commits=gh.commit_list(repo, cfg.max_commits),
                        branches=branches, readme_path=readme, sandbox=sandbox)


def consistency(model, facts: rq.RepoFacts, role: str, n: int, job_id: str) -> Optional[rq.Area]:
    """The model's view of consistency and error handling, or None when there is no code or no model answer."""
    sample = {p: facts.files[p] for p in rq.sample_sources(facts, n)}
    if len(sample) < 2:
        return None
    try:
        got = ask_json(model, "claim_reader", prompt.SYSTEM, prompt.build_user(role, sample),
                       lambda t: parse_model(_Judgement, t), job_id=job_id, temperature=0.1)
    except (SettingsError, FormatError) as err:
        log.info("consistency judgement skipped: %s", err)
        return None
    evidence = [rq.file_evidence(e.path, e.note[:120]) for e in got.evidence if e.path in sample]
    return rq.Area("consistency", got.score, got.summary, evidence[:4])


def save(pool, subject, result: Mapping[str, Any]) -> None:
    """Replace this subject's rows: one per area."""
    col = subject.column
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute(f"DELETE FROM repo_quality WHERE {col} = %s::uuid", (subject.id,))
            for a in result["areas"]:
                conn.execute(
                    f"""INSERT INTO repo_quality ({col}, area, score, summary, evidence)
                        VALUES (%s::uuid, %s, %s, %s, %s::jsonb)""",
                    (subject.id, a["area"], a["score"], a["summary"], json.dumps(a["evidence"])))


@stage("repo_quality")
@never_stall
def repo_quality(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    repo = repo_of(info.repo_url)
    if not repo:
        return {"skipped": True, "reason": "no GitHub repository link was given"}
    run = latest_run(ctx.pool, subject)
    sandbox = {"status": run.status, "recipe_source": (run.recipe or {}).get("source")} if run else None
    gh = GitHubReader(sv.cfg.github_api_base_url, sv.cfg.github_token)
    try:
        facts = read_facts(gh, repo, sv.cfg.repo_quality, sandbox)
    except ToolRefused as err:
        return {"skipped": True, "reason": f"GitHub would not show the repository ({err})"}
    except httpx.HTTPStatusError as err:
        return {"skipped": True, "reason": f"GitHub answered {err.response.status_code}"}
    ctx.check()
    extra = consistency(sv.model, facts, info.role_level, sv.cfg.repo_quality.sample_files, job.id)
    result = rq.judge(facts, info.role_level, extra)
    save(ctx.pool, subject, result)
    return {"repo": repo, "overall": result["overall"], "areas": len(result["areas"]), "files_read": len(facts.files),
            "commits_read": len(facts.commits)}
