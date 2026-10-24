"""Stage `originality`: does the repository match the live site, and does the project look like a public tutorial?

Runs after `github_check` and `claims`, for a hackathon project and a resume project alike. Two parts, each skipped on its
own with a reason when it cannot run (no repository facts, no live link, search off or failing). A skipped part is never
a mark against anyone. Flags are Info or Review only and sit beside the score; they are never subtracted from it.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from talnex_ai.checks import repo_vs_live, tutorial_copy
from talnex_ai.db.jobs import Job
from talnex_ai.llm.prompts import tutorial_copy as prompt
from talnex_ai.llm.structured import ask_json
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.services import get_services
from talnex_ai.worker.subjects import SubjectInfo, load_subject_info, stage_result, subject_of

log = logging.getLogger("talnex.originality")

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
MAX_DEPENDENCY_FILES = 4
README_CHARS = 6000
JUDGE_ROLE = "copy_review"


def _raw(repo: str, branch: str, path: str) -> str:
    return RAW.format(repo=repo, branch=branch, path=path)


def _readme_path(files: list[str]) -> Optional[str]:
    for f in files:
        if "/" not in f and f.lower().startswith("readme"):
            return f
    return None


def _live_address(url: Optional[str]) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None
    return url if "//" in url else "https://" + url


@stage("originality")
def originality(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    subject = subject_of(job)
    info = load_subject_info(ctx.pool, subject)
    facts = stage_result(ctx.pool, job, "github_check") or {}
    if not facts.get("found"):
        return {"skipped": True, "reason": "not checked: " + str(facts.get("reason") or "the repository could not be read")}

    sv = get_services(ctx.pool)
    repo, branch = facts["repo"], facts.get("default_branch") or "main"
    files: list[str] = facts.get("files") or []
    live = _live_address(info.live_url)
    readme_path = _readme_path(files)
    dep_paths = [p for p in (facts.get("dependency_files") or []) if isinstance(p, str)][:MAX_DEPENDENCY_FILES]

    urls = [_raw(repo, branch, p) for p in dep_paths]
    if readme_path:
        urls.append(_raw(repo, branch, readme_path))
    if live:
        urls.append(live)
    try:
        fetched = {r.url: r for r in sv.tinyfish.fetch(urls, fmt="html")} if urls else {}
    except Exception as exc:  # Fetch being down is "could not check", never a failed stage
        log.warning("originality: fetch failed: %s", exc)
        fetched = {}
    ctx.check()

    def text_of(url: str) -> str:
        r = fetched.get(url)
        return r.text if r is not None and r.ok else ""

    readme = text_of(_raw(repo, branch, readme_path)) if readme_path else ""
    result: dict[str, Any] = {
        "repo_vs_live": _repo_vs_live(ctx, info, facts, files, live, dep_paths, repo, branch, fetched, text_of),
        "tutorial_copy": _tutorial_copy(ctx, sv, info, job, repo, readme),
    }
    return result


@stage("tutorial_copy")
def hackathon_originality(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    """The hackathon pipeline calls this stage `tutorial_copy`; it does the same two checks as `originality` (repo vs live site, tutorial copy)."""
    return originality(job, ctx)


def _repo_vs_live(ctx, info: SubjectInfo, facts: dict, files: list[str], live: Optional[str], dep_paths: list[str],
                  repo: str, branch: str, fetched: dict, text_of) -> dict:
    if not live:
        return {"skipped": True, "reason": "there is no live link to compare with"}
    page = fetched.get(live)
    html = page.text if page is not None and page.ok else ""
    if not html:
        return {"skipped": True, "reason": "the live page could not be read, so it was not compared"}

    dep_texts = {p: text_of(_raw(repo, branch, p)) for p in dep_paths}
    dep_texts = {p: t for p, t in dep_texts.items() if t}
    deps_read = bool(dep_paths) and len(dep_texts) == len(dep_paths)
    complete = not facts.get("files_truncated") and bool(files)
    findings = repo_vs_live.compare(
        files=files, languages=facts.get("languages") or {}, dep_names=repo_vs_live.dependency_names(dep_texts),
        deps_read=deps_read, files_complete=complete, live_html=html,
    )
    for f in findings:
        add_flag(ctx.pool, info.kind, info.id, f.flag_type, f.level, f.reason, f.evidence)
    return {"checked": True, "live_marks": repo_vs_live.live_marks(html), "dependency_files_read": sorted(dep_texts),
            "flags": [f.reason for f in findings]}


def _tutorial_copy(ctx, sv, info: SubjectInfo, job: Job, repo: str, readme: str) -> dict:
    title = repo_vs_live.first_heading(readme)
    repo_name = repo.rsplit("/", 1)[-1]
    searches = tutorial_copy.queries(repo_name, title)
    hits = []
    try:
        for q in searches:
            hits += sv.tinyfish.search(q)
    except Exception as exc:  # search off or down: could not check, never a mark against the project
        log.warning("originality: search failed: %s", exc)
        if not hits:
            return {"skipped": True, "reason": f"the web search was not available ({exc}), so tutorial copy was not checked"}
    hits = tutorial_copy.drop_own_pages(hits, repo, info.live_host)
    if not hits:
        return {"checked": True, "match": "none", "reason": "no tutorial or boilerplate page turned up in the search"}
    ctx.check()

    try:
        judgement = ask_json(
            sv.model, JUDGE_ROLE, prompt.SYSTEM,
            prompt.build_user(info.name, readme[:README_CHARS], [(h.title, h.url, h.snippet) for h in hits]),
            lambda text: tutorial_copy.parse_judgement(text, [h.url for h in hits]),
            job_id=job.id,
        )
    except Exception as exc:
        log.warning("originality: tutorial judge failed: %s", exc)
        return {"skipped": True, "reason": "the tutorial-copy judgement could not be made, so it was not checked"}

    flag = tutorial_copy.flag_for(judgement)
    if flag is None:
        return {"checked": True, "match": "none", "searched": searches}
    level, reason, evidence = flag
    add_flag(ctx.pool, info.kind, info.id, "tutorial_copy", level, reason, evidence)
    return {"checked": True, "match": judgement.match, "matched_url": judgement.matched_url, "flag_level": level,
            "label": "possible match, not a verdict"}
