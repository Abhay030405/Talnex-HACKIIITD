"""Read-only, free tools Ask TalNex may call while it answers: fresh facts the saved report does not hold.

Every tool is limited to the subject's own things: its repositories, its live sites' hosts, its coding handles. Nothing
here writes, pays or starts a test (those stay buttons the reviewer presses). What a tool returns is outside text, so the
caller wraps it as untrusted data before a model sees it.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

import httpx

MAX_TEXT = 6000          # characters of one tool result shown to the model
MAX_FILE_BYTES = 8000
TIMEOUT = 15
_REPO = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.IGNORECASE)


class ToolRefused(ValueError):
    """The call is not allowed (unknown tool, a repo or site that is not the subject's) or its input is wrong."""


def repo_of(url: Optional[str]) -> Optional[str]:
    """'owner/name' (lower case) from a GitHub address, or None."""
    m = _REPO.search(url or "")
    return f"{m.group(1)}/{m.group(2).removesuffix('.git')}".lower() if m else None


@dataclass
class Scope:
    """What the tools may touch for one subject."""
    repos: set[str] = field(default_factory=set)
    hosts: set[str] = field(default_factory=set)
    handles: dict[str, str] = field(default_factory=dict)

    def describe(self) -> str:
        return (f"repos: {', '.join(sorted(self.repos)) or 'none'}; sites: {', '.join(sorted(self.hosts)) or 'none'}; "
                f"coding handles: {', '.join(f'{k}={v}' for k, v in sorted(self.handles.items())) or 'none'}")


def scope_for(pool, target_type: str, target_id: str) -> Scope:
    """The subject's repositories, live hosts and coding handles, from the database."""
    with pool.connection() as conn:
        if target_type == "project":
            rows = conn.execute("SELECT live_url, repo_url FROM projects WHERE id = %s::uuid", (target_id,)).fetchall()
            handles: Mapping[str, Any] = {}
        else:
            rows = conn.execute("SELECT live_url, repo_url FROM candidate_projects WHERE candidate_id = %s::uuid",
                                (target_id,)).fetchall()
            got = conn.execute("SELECT coding_handles FROM candidates WHERE id = %s::uuid", (target_id,)).fetchone()
            handles = (got[0] if got else None) or {}
    scope = Scope(handles={k: str(v) for k, v in handles.items() if k in ("leetcode", "codeforces") and v})
    for live, repo in rows:
        if repo_of(repo):
            scope.repos.add(repo_of(repo))
        host = (urlparse(live or "").hostname or "").lower()
        if host:
            scope.hosts.add(host)
    return scope


class GitHubReader:
    """GitHub's official REST API, read only. A 403 (rate limit) or 404 is 'could not read', never an error."""

    def __init__(self, base_url: str, token: str = "", http: Optional[httpx.Client] = None):
        self.base = base_url.rstrip("/")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "talnex"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = http or httpx.Client(timeout=TIMEOUT, headers=headers)
        self.headers = headers

    def _get(self, path: str, **params) -> Any:
        r = self.http.get(f"{self.base}{path}", params=params or None, headers=self.headers)
        if r.status_code in (403, 404, 409, 451):
            raise ToolRefused(f"GitHub could not read {path} ({r.status_code})")
        r.raise_for_status()
        return r.json()

    def commits(self, repo: str, n: int = 10) -> str:
        rows = self._get(f"/repos/{repo}/commits", per_page=n)
        return "\n".join(f"{c['sha'][:7]} {c['commit']['author'].get('date', '')} {c['commit']['author'].get('name', '')}: "
                         f"{(c['commit'].get('message') or '').splitlines()[0][:120]}" for c in rows) or "no commits"

    def contributors(self, repo: str) -> str:
        rows = self._get(f"/repos/{repo}/contributors", per_page=20)
        return "\n".join(f"{c.get('login')}: {c.get('contributions')} commits" for c in rows) or "no contributors"

    def info(self, repo: str) -> str:
        r = self._get(f"/repos/{repo}")
        langs = self._get(f"/repos/{repo}/languages")
        return (f"{r.get('full_name')}: stars {r.get('stargazers_count')}, forks {r.get('forks_count')}, default branch "
                f"{r.get('default_branch')}, created {r.get('created_at')}, last push {r.get('pushed_at')}, fork: "
                f"{r.get('fork')}, languages: {', '.join(langs) or 'none'}")

    def file(self, repo: str, path: str) -> str:
        if not path or ".." in path or path.startswith("/"):
            raise ToolRefused("give a file path inside the repository")
        r = self._get(f"/repos/{repo}/contents/{path}")
        if not isinstance(r, Mapping) or r.get("type") != "file":
            raise ToolRefused(f"{path} is not a file")
        return base64.b64decode(r.get("content") or "").decode("utf-8", "replace")[:MAX_FILE_BYTES]


class Tools:
    """Runs one tool call inside the subject's scope. Returns (text for the model, a short 'what' for the source chip)."""

    NAMES = ("github", "fetch_page", "coding_profile")

    def __init__(self, scope: Scope, *, github: Optional[GitHubReader] = None,
                 fetch: Optional[Callable[[list[str]], list]] = None,
                 leetcode: Optional[Callable[[str], tuple]] = None,
                 codeforces: Optional[Callable[[str], str]] = None):
        self.scope, self.github, self.fetch, self.leetcode, self.codeforces = scope, github, fetch, leetcode, codeforces

    def run(self, name: str, args: Mapping[str, Any]) -> tuple[str, str]:
        if name not in self.NAMES:
            raise ToolRefused(f"unknown tool {name!r}")
        text, what = getattr(self, f"_{name}")(args or {})
        return text[:MAX_TEXT], what

    def _github(self, args: Mapping[str, Any]) -> tuple[str, str]:
        repo = repo_of(f"github.com/{args.get('repo', '')}")   # "owner/name" or a full GitHub address
        if not repo or repo not in self.scope.repos:
            raise ToolRefused(f"only the subject's repositories can be read ({', '.join(sorted(self.scope.repos)) or 'none'})")
        if self.github is None:
            raise ToolRefused("GitHub is not available")
        what = str(args.get("what") or "commits")
        if what == "commits":
            return self.github.commits(repo), f"latest commits of {repo}"
        if what == "contributors":
            return self.github.contributors(repo), f"contributors of {repo}"
        if what == "info":
            return self.github.info(repo), f"{repo} details"
        if what == "file":
            path = str(args.get("path") or "")
            return self.github.file(repo, path), f"{repo}/{path}"
        raise ToolRefused("what must be commits, contributors, info or file")

    def _fetch_page(self, args: Mapping[str, Any]) -> tuple[str, str]:
        url = str(args.get("url") or "")
        host = (urlparse(url).hostname or "").lower()
        if not host or host not in self.scope.hosts or urlparse(url).scheme not in ("http", "https"):
            raise ToolRefused(f"only the subject's own live sites can be read ({', '.join(sorted(self.scope.hosts)) or 'none'})")
        if self.fetch is None:
            raise ToolRefused("page reading is not available")
        (res,) = self.fetch([url])
        if not res.ok:
            return f"the page did not load ({res.error_code or res.http_status})", f"page {url}"
        return f"{res.title or ''}\n{res.text or ''}", f"page {url}"

    def _coding_profile(self, args: Mapping[str, Any]) -> tuple[str, str]:
        site = str(args.get("site") or "")
        handle = self.scope.handles.get(site)
        if not handle:
            raise ToolRefused(f"no {site or 'such'} handle for this candidate")
        if site == "leetcode" and self.leetcode:
            outcome, facts = self.leetcode(handle)
            return (str(facts) if outcome == "ok" else f"could not read ({outcome})"), f"LeetCode {handle}"
        if site == "codeforces" and self.codeforces:
            return self.codeforces(handle), f"Codeforces {handle}"
        raise ToolRefused(f"{site} is not available")


def codeforces_reader(base_url: str, http: Optional[httpx.Client] = None) -> Callable[[str], str]:
    """Current Codeforces rating, rank and the last few rated contests, from the public API."""
    client = http or httpx.Client(timeout=TIMEOUT)

    def read(handle: str) -> str:
        info = client.get(f"{base_url.rstrip('/')}/user.info", params={"handles": handle}).json()
        if info.get("status") != "OK":
            return f"could not read ({info.get('comment', 'not found')})"
        u = info["result"][0]
        rating = client.get(f"{base_url.rstrip('/')}/user.rating", params={"handle": handle}).json()
        recent = (rating.get("result") or [])[-5:] if rating.get("status") == "OK" else []
        return (f"rating {u.get('rating')}, max {u.get('maxRating')}, rank {u.get('rank')}; last contests: "
                + "; ".join(f"{c['contestName']} rank {c['rank']} {c['oldRating']}->{c['newRating']}" for c in recent))
    return read
