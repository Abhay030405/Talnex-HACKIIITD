"""Repository engineering quality: how the submitted repo is built as engineering work, beside the feature scores.

Plain code over facts read from GitHub (the file tree, a few key files, recent commits). Each area gets a score out of
10 and 2-4 pieces of evidence that point at a real file or commit; evidence that does not exist in the facts is dropped,
so nothing is ever invented. The role level decides what is expected: a fresher is never marked down for missing
enterprise practices (CI, type checking, containers), only credited for having them. Evidence only: it is never
subtracted from any feature score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

LEVELS = ("fresher", "junior", "mid", "senior")
LARGE_FILE_BYTES = 32_000          # about 800 lines of code
CODE = re.compile(r"\.(py|js|jsx|ts|tsx|go|java|kt|rb|php|rs|cs|c|cc|cpp|swift|dart|vue|svelte)$", re.I)
TEST = re.compile(r"(^|/)(tests?|__tests__|spec)/|(_test|\.test|\.spec|_spec)\.[a-z]+$|(^|/)test_[^/]+\.py$", re.I)
CI = re.compile(r"^(\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.yml|\.circleci/config\.yml|azure-pipelines\.yml|"
                r"Jenkinsfile|\.travis\.yml|bitbucket-pipelines\.yml)$")
LINT = re.compile(r"(^|/)(\.eslintrc(\.[a-z]+)?|eslint\.config\.[a-z]+|\.prettierrc(\.[a-z]+)?|prettier\.config\.[a-z]+|"
                  r"\.flake8|ruff\.toml|\.ruff\.toml|\.pylintrc|\.golangci\.ya?ml|\.editorconfig|biome\.json|"
                  r"\.rubocop\.yml)$")
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "poetry.lock", "Pipfile.lock",
             "uv.lock", "go.sum", "Cargo.lock", "Gemfile.lock", "composer.lock"}
DEPLOY = re.compile(r"(^|/)(Dockerfile|docker-compose\.ya?ml|compose\.ya?ml|Procfile|vercel\.json|netlify\.toml|"
                    r"fly\.toml|render\.yaml|app\.yaml|serverless\.ya?ml)$|(^|/)(k8s|helm|terraform)/")
GENERATED = re.compile(r"(^|/)(node_modules|dist|build|\.next|out|target|__pycache__|venv|\.venv|env)/|\.pyc$|"
                       r"\.DS_Store$")
API_DOCS = re.compile(r"(^|/)(openapi|swagger)[^/]*\.(ya?ml|json)$|(^|/)docs/[^/]*api", re.I)
LOW_INFO = re.compile(r"^(fix(es|ed)?|update[sd]?|wip|changes?|commit|test|minor|stuff|misc|done|final|edit(s|ed)?|"
                      r"\.+|[a-z]|initial commit|first commit|add files via upload|update readme(\.md)?)\W*$", re.I)
CONVENTIONAL = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: \S", re.I)
SECRET_VALUE = re.compile(r"(?im)^\s*[A-Z0-9_]*(SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*=\s*[^\s#]{8,}")


@dataclass
class RepoFacts:
    """What was read from GitHub. `files` holds the text of the few files that were read; `sizes` every blob's size."""
    paths: list[str]
    sizes: dict[str, int] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    commits: list[dict] = field(default_factory=list)   # {sha, message, date, author}
    branches: int = 1
    readme_path: Optional[str] = None
    sandbox: Optional[Mapping[str, Any]] = None          # the latest sandbox run: status, recipe_source


@dataclass
class Area:
    area: str
    score: float
    summary: str
    evidence: list[dict]

    def as_dict(self) -> dict:
        return {"area": self.area, "score": round(self.score, 1), "summary": self.summary, "evidence": self.evidence}


def file_evidence(path: str, note: str) -> dict:
    return {"kind": "file", "path": path, "note": note}


def _commit(c: Mapping[str, Any], note: str) -> dict:
    return {"kind": "commit", "sha": str(c.get("sha", ""))[:7], "message": _subject(c)[:100], "note": note}


def _subject(c: Mapping[str, Any]) -> str:
    return (str(c.get("message") or "").splitlines() or [""])[0].strip()


def _ratio_score(earned: float, possible: float) -> float:
    return 10.0 * earned / possible if possible else 0.0


def _level(role: str) -> int:
    return LEVELS.index(role) if role in LEVELS else 0


def production(f: RepoFacts, role: str) -> Area:
    """Tests, CI that runs them, lint and type checking, deploy config, env handling and pinned dependencies."""
    paths, ev, notes = f.paths, [], []
    code = [p for p in paths if CODE.search(p) and not GENERATED.search(p)]
    tests = [p for p in code if TEST.search(p)]
    ci = [p for p in paths if CI.search(p)]
    ci_runs_tests = any(re.search(r"\b(test|pytest|jest|vitest|go test|cargo test|npm (run )?test|mocha)\b", f.files.get(p, ""))
                        for p in ci)
    lint = [p for p in paths if LINT.search(p)]
    tsconfig = f.files.get("tsconfig.json", "")
    typed = ('"strict":true' in re.sub(r"\s", "", tsconfig)
             or any(p in paths for p in ("mypy.ini", "pyrightconfig.json")) or "[tool.mypy]" in f.files.get("pyproject.toml", ""))
    deploy = [p for p in paths if DEPLOY.search(p)]
    env_example = [p for p in paths if re.search(r"(^|/)\.env\.(example|sample|template)$", p)]
    committed_env = [p for p in paths if re.search(r"(^|/)\.env(\.local|\.production)?$", p)]
    leaked = [p for p, text in f.files.items() if SECRET_VALUE.search(text) and not p.endswith((".example", ".sample", ".template"))]
    locks = [p for p in paths if p.rsplit("/", 1)[-1] in LOCKFILES]

    # (present, weight, enterprise) — enterprise items are only credited, never required, for a fresher
    share = len(tests) / len(code) if code else 0.0
    items = [
        (min(share / 0.2, 1.0) if tests else 0.0, 3, False),
        (1.0 if locks else 0.0, 1, False),
        (1.0 if env_example and not committed_env and not leaked else (0.5 if not committed_env and not leaked else 0.0), 1, False),
        (1.0 if ci else 0.0, 2, True),
        (1.0 if ci_runs_tests else 0.0, 1, True),
        (1.0 if lint else 0.0, 1, True),
        (1.0 if typed else 0.0, 1, True),
        (1.0 if deploy else 0.0, 1, True),
    ]
    fresher = _level(role) == 0
    earned = sum(v * w for v, w, _ in items)
    possible = sum(w for v, w, ent in items if not (fresher and ent and v == 0))
    if tests:
        ev.append(file_evidence(tests[0], f"{len(tests)} test files for {len(code)} code files ({share:.0%})"))
    else:
        notes.append("no tests found")
    if ci:
        ev.append(file_evidence(ci[0], "CI runs the tests" if ci_runs_tests else "CI is set up but does not run tests"))
    else:
        notes.append("no CI")
    if lint:
        ev.append(file_evidence(lint[0], "lint or format config"))
    if deploy:
        ev.append(file_evidence(deploy[0], "deploy or container config"))
    if committed_env:
        ev.append(file_evidence(committed_env[0], "an .env file is committed"))
    if leaked:
        ev.append(file_evidence(leaked[0], "a secret-looking value is committed (masked, never stored)"))
    if locks:
        ev.append(file_evidence(locks[0], "dependencies pinned by a lockfile"))
    else:
        notes.append("no lockfile")
    good = [n for n, ok in (("tests", tests), ("CI", ci), ("lint", lint), ("type checking", typed), ("deploy config", deploy)) if ok]
    summary = (f"Has {', '.join(good)}." if good else "No tests, CI, lint or deploy config found.") + \
              (f" Missing: {', '.join(notes)}." if notes else "")
    return Area("production", min(_ratio_score(earned, possible), 10.0), summary, ev[:4])


def structure(f: RepoFacts, role: str) -> Area:
    """A layout that fits the stack, no giant files, nothing generated committed."""
    code = [p for p in f.paths if CODE.search(p) and not GENERATED.search(p)]
    generated = sorted({re.split(r"/", p)[0] if "/" in p else p for p in f.paths if GENERATED.search(p)})
    giants = sorted((p for p in code if f.sizes.get(p, 0) > LARGE_FILE_BYTES), key=lambda p: -f.sizes.get(p, 0))
    root_code = [p for p in code if "/" not in p]
    folders = {p.split("/")[0] for p in code if "/" in p}
    score, ev = 10.0, []
    if generated:
        score -= 3
        ev.append(file_evidence(generated[0], "generated or dependency files are committed"))
    if giants:
        score -= min(3.0, 1.0 * len(giants))
        ev.append(file_evidence(giants[0], f"a very large file (about {f.sizes[giants[0]] // 40} lines)"))
    if len(root_code) > 15 and len(folders) < 2:
        score -= 2
        ev.append(file_evidence(root_code[0], f"{len(root_code)} code files sit flat at the top of the repo"))
    if folders:
        top = sorted(folders, key=lambda d: -sum(1 for p in code if p.startswith(d + "/")))[0]
        ev.append(file_evidence(top + "/", f"code is organised in folders ({', '.join(sorted(folders)[:4])})"))
    if not code:
        return Area("structure", 0.0, "No source code was found in the repository.", [])
    summary = ("Clean layout." if score >= 8 else "Layout has issues.") + \
              (f" {len(giants)} very large files." if giants else "") + (" Generated files are committed." if generated else "")
    return Area("structure", max(score, 0.0), summary, ev[:4])


def hygiene(f: RepoFacts, role: str) -> Area:
    """README with setup, run and config sections, a licence, a .gitignore, branches beyond the default."""
    readme = f.files.get(f.readme_path or "", "") if f.readme_path else ""
    lower = readme.lower()
    sections = {"setup": bool(re.search(r"install|setup|getting started|prerequisites", lower)),
                "run": bool(re.search(r"\b(usage|run|start|how to use)\b", lower)),
                "config": bool(re.search(r"\.env|environment|config", lower))}
    licence = next((p for p in f.paths if re.match(r"(?i)^(license|licence|copying)(\.[a-z]+)?$", p)), None)
    ignore = ".gitignore" in f.paths
    earned = (3 if len(readme) > 400 else 1.5 if readme else 0) + sum(sections.values()) + \
             (1.5 if licence else 0) + (1.5 if ignore else 0) + (1 if f.branches > 1 else 0)
    ev = []
    if f.readme_path:
        found = [k for k, v in sections.items() if v]
        ev.append(file_evidence(f.readme_path, f"README ({len(readme)} characters; covers {', '.join(found) or 'no setup or run steps'})"))
    if licence:
        ev.append(file_evidence(licence, "licence"))
    if ignore:
        ev.append(file_evidence(".gitignore", "ignores build and dependency files"))
    summary = ("README explains setup and running." if sections["setup"] and sections["run"] else
               "README is missing setup or run steps." if readme else "No README.") + \
              ("" if licence else " No licence.") + (" Uses branches." if f.branches > 1 else " Everything on one branch.")
    return Area("hygiene", min(_ratio_score(earned, 10), 10.0), summary, ev[:4])


def commits_area(f: RepoFacts, role: str) -> Area:
    """Message quality, conventional commits, and work spread over time instead of one burst."""
    rows = [c for c in f.commits if _subject(c)]
    if not rows:
        return Area("commits", 0.0, "No commits could be read.", [])
    low = [c for c in rows if LOW_INFO.match(_subject(c)) or len(_subject(c)) < 6]
    conv = [c for c in rows if CONVENTIONAL.match(_subject(c))]
    days: dict[str, int] = {}
    for c in rows:
        day = str(c.get("date") or "")[:10]
        if day:
            days[day] = days.get(day, 0) + 1
    busiest = max(days.values()) / len(rows) if days else 1.0
    low_share, conv_share = len(low) / len(rows), len(conv) / len(rows)
    score = 10.0 * (1 - low_share) * 0.6 + 10.0 * min(conv_share / 0.5, 1.0) * 0.15 + \
            10.0 * (1 - busiest if len(days) > 1 else 0.0) * 0.25
    ev = []
    good = next((c for c in rows if c not in low and len(_subject(c)) >= 20), None)
    if good:
        ev.append(_commit(good, "a clear commit message"))
    if low:
        ev.append(_commit(low[0], f"{len(low)} of {len(rows)} messages say little ({low_share:.0%})"))
    if conv:
        ev.append(_commit(conv[0], f"conventional commits in {conv_share:.0%} of messages"))
    burst_day = max(days, key=days.get) if days else ""
    if busiest >= 0.6 and len(rows) >= 5:
        ev.append(_commit(next(c for c in rows if str(c.get("date", ""))[:10] == burst_day),
                          f"{busiest:.0%} of the commits landed on {burst_day}"))
    summary = f"{len(rows)} recent commits over {len(days)} days; {low_share:.0%} say little" + \
              (f", {conv_share:.0%} follow conventional commits." if conv else ".")
    return Area("commits", max(min(score, 10.0), 0.0), summary, ev[:4])


def docs_area(f: RepoFacts, role: str) -> Optional[Area]:
    """API docs for a backend repo, and whether the README's setup worked in the VM. None when neither applies."""
    spec = next((p for p in f.paths if API_DOCS.search(p)), None)
    backend = any(re.search(r"(express|fastify|koa|hono|flask|fastapi|django|gin|echo|fiber|spring|nestjs|aiohttp)",
                            f.files.get(p, ""), re.I) for p in ("package.json", "requirements.txt", "pyproject.toml", "go.mod"))
    sb = f.sandbox or {}
    if not backend and not sb:
        return None
    score, ev, bits = 5.0, [], []
    if backend:
        if spec:
            score += 3
            ev.append(file_evidence(spec, "an API spec or API docs"))
            bits.append("has API docs")
        else:
            bits.append("a backend with no API spec")
    if sb:
        ran = sb.get("status") in ("running", "done")
        from_readme = str(sb.get("recipe_source") or "") == "readme"
        if ran and from_readme:
            score += 2
            bits.append("the README's setup worked in a fresh VM")
        elif ran:
            bits.append("it ran in a VM, but not by following the README")
        else:
            score -= 2
            bits.append("it could not be started in a fresh VM")
        if f.readme_path:
            ev.append(file_evidence(f.readme_path, "setup steps the VM followed" if from_readme else "setup steps"))
    return Area("docs", max(min(score, 10.0), 0.0), "; ".join(bits).capitalize() + ".", ev[:4])


def keep_real(area: Area, f: RepoFacts) -> Area:
    """Drop evidence that does not point at a real file, folder or commit in the facts: never show invented proof."""
    shas = {str(c.get("sha", ""))[:7] for c in f.commits}
    folders = {p.split("/")[0] + "/" for p in f.paths if "/" in p}
    real = [e for e in area.evidence
            if (e.get("kind") == "commit" and e.get("sha") in shas)
            or (e.get("kind") == "file" and (e.get("path") in f.paths or e.get("path") in folders))]
    return Area(area.area, area.score, area.summary, real[:4])


def judge(f: RepoFacts, role: str, consistency: Optional[Area] = None) -> dict:
    """Every area, the evidence checked against the facts, and the overall score (the mean)."""
    areas = [production(f, role), structure(f, role), hygiene(f, role), commits_area(f, role)]
    docs = docs_area(f, role)
    if docs:
        areas.append(docs)
    if consistency:
        areas.append(consistency)
    areas = [keep_real(a, f) for a in areas]
    overall = round(sum(a.score for a in areas) / len(areas), 1) if areas else None
    return {"areas": [a.as_dict() for a in areas], "overall": overall}


def sample_sources(f: RepoFacts, n: int) -> list[str]:
    """The code files to show the model for consistency: the biggest non-test, non-generated ones that were read."""
    code = [p for p in f.files if CODE.search(p) and not TEST.search(p) and not GENERATED.search(p)]
    return sorted(code, key=lambda p: -len(f.files[p]))[:n]


def pick_files(paths: Sequence[str], sizes: Mapping[str, int], max_files: int) -> list[str]:
    """Which files to read: the key config files, the README, CI files, then the largest source files."""
    key = [p for p in paths if p in ("package.json", "tsconfig.json", "pyproject.toml", "requirements.txt", "go.mod",
                                      "setup.cfg", "Cargo.toml") or CI.search(p)
           or re.match(r"(?i)^readme(\.[a-z]+)?$", p) or re.search(r"(^|/)\.env(\..*)?$", p)]
    code = sorted((p for p in paths if CODE.search(p) and not TEST.search(p) and not GENERATED.search(p)
                   and sizes.get(p, 0) <= LARGE_FILE_BYTES * 2), key=lambda p: -sizes.get(p, 0))
    out: list[str] = []
    for p in key + code:
        if p not in out:
            out.append(p)
    return out[:max_files]
