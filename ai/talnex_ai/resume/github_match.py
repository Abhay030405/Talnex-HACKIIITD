"""A resume project with no repository link: look for it among the person's own public GitHub repositories.

A repo counts when its name is the project's name (spaces and punctuation ignored), when its homepage is the project's
live link, or, for a name of 5 or more letters, when one name holds the other. Forks only match on the exact name. The
recruiter sees the link on the confirm page and can change or remove it before anything is checked."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Optional
from urllib.parse import urlparse

from talnex_ai.resume.reader import Project


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _title(name: str) -> str:
    """The project's own name, without the tagline: "MarlOS — Multi-Agent ..." gives "MarlOS"."""
    return re.split(r"\s+[—–\-|:]\s+|:\s", name, maxsplit=1)[0]


def _host(url: str) -> str:
    return (urlparse(url if "//" in url else f"https://{url}").hostname or "").lower().removeprefix("www.")


def find_repo(project: Project, repos: list[dict]) -> Optional[str]:
    title = _norm(_title(project.name))
    live = _host(project.live_url) if project.live_url else ""
    exact = [r for r in repos if title and _norm(r["name"]) == title]
    if exact:
        return exact[0]["url"]
    if live:
        for r in repos:
            if r.get("homepage") and _host(r["homepage"]) == live:
                return r["url"]
    if len(title) >= 5:
        for r in repos:
            name = _norm(r["name"])
            if not r.get("fork") and len(name) >= 5 and (name in title or title in name):
                return r["url"]
    return None


def fill_missing_repos(projects: list[Project], repos: list[dict]) -> tuple[list[Project], list[str]]:
    """The projects with a repo link filled in where one was found, and the names of the projects that got one."""
    out, filled = [], []
    taken = {p.repo_url.rstrip("/").lower() for p in projects if p.repo_url}
    for p in projects:
        url = None if p.repo_url else find_repo(p, [r for r in repos if r["url"].rstrip("/").lower() not in taken])
        if url:
            taken.add(url.rstrip("/").lower())
            filled.append(p.name)
            p = replace(p, repo_url=url)
        out.append(p)
    return out, filled


def _demo() -> None:
    repos = [{"name": "MarlOS", "url": "https://github.com/a/MarlOS", "homepage": "", "fork": False},
             {"name": "notes", "url": "https://github.com/a/notes", "homepage": "https://notebox.vercel.app", "fork": False},
             {"name": "psyqueue-core", "url": "https://github.com/a/psyqueue-core", "homepage": "", "fork": False},
             {"name": "react", "url": "https://github.com/a/react", "homepage": "", "fork": True}]
    mk = lambda name, live=None, repo=None: Project(name, (), live, repo, None)  # noqa: E731
    got, filled = fill_missing_repos([mk("MarlOS — Multi-Agent OS"), mk("NoteBox - quick notes", "https://notebox.vercel.app"),
                                      mk("PsyQueue — Job Queue"), mk("React Clone"), mk("Has one", repo="https://github.com/a/x")], repos)
    assert [p.repo_url for p in got] == ["https://github.com/a/MarlOS", "https://github.com/a/notes",
                                        "https://github.com/a/psyqueue-core", None, "https://github.com/a/x"], got
    assert filled == ["MarlOS — Multi-Agent OS", "NoteBox - quick notes", "PsyQueue — Job Queue"]


if __name__ == "__main__":
    _demo()
    print("ok")
