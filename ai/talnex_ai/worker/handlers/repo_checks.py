"""Stage `repo_checks` (hackathon): turn what the repository shows into red flags.

Waits for the Go stages `github_check`, `event_dates` and `sponsor_files`. It reads their saved facts, then reads a few
code files with a free TinyFish Fetch to see whether each sponsor tool is really called. Flags sit beside the score and
are never subtracted from it. The repository-vs-live-site comparison is not part of the hackathon pipeline yet; the
result says so, with the reason.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from talnex_ai.checks.event_dates import date_flags
from talnex_ai.checks.sponsor_usage import candidate_source_files, decide, find_uses, mentioned
from talnex_ai.db.jobs import Job
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import load_subject_info, stage_result, subject_of

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def _raw(repo: str, branch: str, path: str) -> str:
    return RAW.format(repo=repo, branch=branch, path=path)


def _readme_path(files: list[str]) -> Optional[str]:
    for f in files:
        if "/" not in f and f.lower().startswith("readme"):
            return f
    return None


@stage("repo_checks")
def repo_checks(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    if subject.kind != "project":
        return {"skipped": True, "reason": "these repository checks are for hackathon projects"}
    info = load_subject_info(ctx.pool, subject)

    repo_facts = stage_result(ctx.pool, job, "github_check") or {}
    dates = stage_result(ctx.pool, job, "event_dates") or {}
    sponsors = stage_result(ctx.pool, job, "sponsor_files") or {}
    result: dict[str, Any] = {"repo_vs_live": {"skipped": True, "reason": (
        "no repository link was given" if not info.repo_url else
        "comparing the repository with the live site runs for resume projects only for now")}}

    added = []
    for f in date_flags(dates):
        if add_flag(ctx.pool, info.kind, info.id, f.flag_type, f.level, f.reason, f.evidence):
            added.append(f.flag_type)
    result["date_flags"] = [f.flag_type for f in date_flags(dates)]
    if not dates.get("found"):
        result["dates_not_checked"] = dates.get("reason", "no repository data")

    tools = sponsors.get("tools") or []
    if sponsors.get("skipped") or not tools:
        result["sponsors"] = sponsors.get("reason") or "no sponsor tools to check"
        return result
    if not repo_facts.get("found"):
        result["sponsors"] = "not checked: " + str(repo_facts.get("reason") or "the repository could not be read")
        return result

    sv = get_services(ctx.pool)
    repo, branch = repo_facts["repo"], repo_facts["default_branch"]
    files: list[str] = repo_facts.get("files") or []
    chosen = candidate_source_files(files)
    readme_path = _readme_path(files)
    urls = [_raw(repo, branch, p) for p in chosen] + ([_raw(repo, branch, readme_path)] if readme_path else [])
    # "html" returns a plain file exactly as written; "markdown" would rewrite code (it escapes underscores).
    fetched = sv.tinyfish.fetch(urls, fmt="html") if urls else []
    by_url = {r.url: r for r in fetched}
    texts = {p: by_url[_raw(repo, branch, p)].text for p in chosen if by_url.get(_raw(repo, branch, p)) and by_url[_raw(repo, branch, p)].ok}
    readme = by_url[_raw(repo, branch, readme_path)].text if readme_path and by_url.get(_raw(repo, branch, readme_path)) and by_url[_raw(repo, branch, readme_path)].ok else ""
    ctx.check()

    # We cannot call a tool "unused" if we did not see all of the code: the file list was cut short, more source files
    # exist than we read, or some of the ones we asked for did not load.
    everything = candidate_source_files(files, limit=len(files) or 1)
    partial = bool(repo_facts.get("files_truncated")) or len(texts) < len(everything)

    verdicts = []
    for entry in tools:
        tool = entry["tool"]
        uses = find_uses(tool, texts)
        v = decide(tool, listed=bool(entry.get("listed")), used=bool(uses), in_readme=mentioned(tool, readme), partial=partial)
        verdicts.append({"tool": tool, "listed": v.listed, "used": v.used, "in_readme": v.in_readme, "flag": v.level})
        if v.level:
            add_flag(ctx.pool, info.kind, info.id, "sponsor_tech_not_used", v.level, v.reason,
                     {"tool": tool, "listed_in": entry.get("matches", []), "code_files_read": len(texts),
                      "code_files_chosen": len(chosen), "partial": partial})
    result["sponsors"] = verdicts
    result["code_files_read"] = len(texts)
    return result
