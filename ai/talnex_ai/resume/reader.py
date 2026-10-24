"""The resume reader: resume text in, the projects on it (with links and bullets) and coding handles out.

A model reads the text, then plain code checks its answer against the text. Anything the model reports that is not
actually on the resume (a project, a link, a bullet, a handle) is dropped, so a made-up project can never reach a test.
Links are sorted into live app, repository and video by what they point at, not by what the model called them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats import parse_model
from talnex_ai.llm.prompts.resume_reader import SYSTEM, user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.safety.hidden_instructions import Finding, find_hidden_instructions

log = logging.getLogger("talnex.resume")

MAX_PROJECTS = 8
MAX_BULLETS = 8
MAX_BULLET_CHARS = 400
CODING_SITES = ("codeforces", "leetcode", "codechef")

_REPO_HOSTS = {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org"}
_VIDEO_HOSTS = ("youtube.com", "youtu.be", "loom.com", "vimeo.com", "drive.google.com")
_HANDLE = re.compile(r"^[A-Za-z0-9_.\-]{2,40}$")
_WORD = re.compile(r"[a-z0-9]+")

# A coding profile address, with the handle in it. The first group is always the handle.
_PROFILE_LINKS = {
    "codeforces": re.compile(r"codeforces\.com/profile/([A-Za-z0-9_.\-]{2,40})", re.IGNORECASE),
    "leetcode": re.compile(r"leetcode\.com/(?:u/)?([A-Za-z0-9_.\-]{2,40})(?![A-Za-z0-9_.\-])", re.IGNORECASE),
    "codechef": re.compile(r"codechef\.com/users/([A-Za-z0-9_.\-]{2,40})", re.IGNORECASE),
}
_LEETCODE_NOT_PEOPLE = {"problems", "problemset", "contest", "explore", "discuss", "store", "interview", "studyplan",
                        "accounts", "subscribe", "assessment", "u", "tag", "company"}
PROFILE_URL = {
    "codeforces": "https://codeforces.com/profile/{}",
    "leetcode": "https://leetcode.com/u/{}",
    "codechef": "https://www.codechef.com/users/{}",
}


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class RawProject(_Raw):
    name: str = Field(min_length=1, max_length=120)
    bullets: list[str] = Field(default_factory=list)
    live_url: Optional[str] = None
    repo_url: Optional[str] = None
    video_url: Optional[str] = None


class RawResume(_Raw):
    projects: list[RawProject] = Field(default_factory=list)
    coding_handles: dict[str, Optional[str]] = Field(default_factory=dict)
    github_username: Optional[str] = None


@dataclass(frozen=True)
class Project:
    name: str
    bullets: tuple[str, ...]
    live_url: Optional[str]
    repo_url: Optional[str]
    video_url: Optional[str]


@dataclass
class ResumeRead:
    projects: list[Project]
    coding_handles: dict[str, str]
    github_username: Optional[str]
    coding_links: dict[str, str] = field(default_factory=dict)  # the profile address, only for sites where one was on the resume
    findings: list[Finding] = field(default_factory=list)    # hidden instructions found in the resume text
    dropped: list[str] = field(default_factory=list)          # what was reported but not on the resume


# ------------------------------------------------------------------------------------------ checks against the text


def _compact(text: str) -> str:
    """Lower case with all spaces and line breaks removed, so a link wrapped over two lines still matches."""
    return re.sub(r"\s+", "", text.lower())


def _clean_url(raw: str) -> Optional[str]:
    url = raw.strip().rstrip(".,;:!?)>]'\"")
    if not url:
        return None
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        return None
    return url


def _bare(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() + parsed.path.rstrip("/").lower() + (("?" + parsed.query.lower()) if parsed.query else "")


def kind_of(url: str) -> Optional[str]:
    """'repo', 'video' or 'live' by what the link points at; None for links that are none of these (like a GitHub profile)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    segments = [s for s in parsed.path.split("/") if s]
    if host in _REPO_HOSTS:
        return "repo" if len(segments) >= 2 else None
    if any(host == h or host.endswith("." + h) for h in _VIDEO_HOSTS):
        return "video"
    return "live"


def _supported(sentence: str, words_in_text: set[str]) -> bool:
    """A bullet counts only if most of its meaningful words are really on the resume."""
    tokens = [w for w in _WORD.findall(sentence.lower()) if len(w) >= 4]
    if not tokens:
        return True
    return sum(1 for w in tokens if w in words_in_text) / len(tokens) >= 0.7


def profile_links_in(text: str) -> dict[str, tuple[str, str]]:
    """Coding profile addresses written (or linked) in the resume: site -> (handle, address). Plain pattern matching,
    so an address is never invented. The first one found for a site wins."""
    found: dict[str, tuple[str, str]] = {}
    for site, pattern in _PROFILE_LINKS.items():
        for match in pattern.finditer(text):
            handle = match.group(1).rstrip(".")
            if site == "leetcode" and handle.lower() in _LEETCODE_NOT_PEOPLE:
                continue
            if _HANDLE.match(handle):
                found[site] = (handle, PROFILE_URL[site].format(handle))
                break
    return found


def validate(raw: RawResume, text: str) -> ResumeRead:
    """Keep only what the resume text really supports."""
    compact = _compact(text)
    lowered = text.lower()
    words = set(_WORD.findall(lowered))
    result = ResumeRead(projects=[], coding_handles={}, github_username=None)

    seen: set[str] = set()
    for item in raw.projects:
        name = re.sub(r"\s+", " ", item.name).strip()
        key = name.lower()
        if not name or key in seen:
            continue
        if key not in re.sub(r"\s+", " ", lowered):
            result.dropped.append(f"project not on the resume: {name}")
            continue
        seen.add(key)

        found: dict[str, str] = {}
        for candidate in (item.live_url, item.repo_url, item.video_url):
            url = _clean_url(candidate) if candidate else None
            if url is None:
                continue
            if _bare(url) not in compact:
                result.dropped.append(f"link not on the resume: {url}")
                continue
            kind = kind_of(url)
            if kind and kind not in found:
                found[kind] = url

        bullets: list[str] = []
        for bullet in item.bullets[:MAX_BULLETS]:
            sentence = re.sub(r"\s+", " ", bullet).strip()[:MAX_BULLET_CHARS]
            if not sentence:
                continue
            if _supported(sentence, words):
                bullets.append(sentence)
            else:
                result.dropped.append(f"bullet not on the resume: {sentence[:60]}")
        result.projects.append(Project(name, tuple(bullets), found.get("live"), found.get("repo"), found.get("video")))
        if len(result.projects) == MAX_PROJECTS:
            break

    for site in CODING_SITES:
        handle = (raw.coding_handles.get(site) or "").strip()
        if handle and _HANDLE.match(handle) and handle.lower() in compact:
            result.coding_handles[site] = handle
        elif handle:
            result.dropped.append(f"handle not on the resume: {site} {handle}")
    # An address on the resume is the surest source: it gives the handle and the link together.
    for site, (handle, link) in profile_links_in(text).items():
        result.coding_handles[site] = handle
        result.coding_links[site] = link
    username = (raw.github_username or "").strip().lstrip("@")
    if username and _HANDLE.match(username) and username.lower() in compact:
        result.github_username = username
    elif username:
        result.dropped.append(f"GitHub name not on the resume: {username}")
    return result


def read_resume(client: ChatClient, text: str, *, job_id: Optional[str] = None) -> ResumeRead:
    """Read a resume's text. The text is data, never instructions; hidden instructions in it are reported."""
    raw = ask_json(client, "claim_reader", SYSTEM, user(text), lambda t: parse_model(RawResume, t), job_id=job_id)
    result = validate(raw, text)
    result.findings = find_hidden_instructions(text)
    if result.dropped:
        log.info("resume reader dropped %d item(s) that were not on the resume", len(result.dropped))
    return result
