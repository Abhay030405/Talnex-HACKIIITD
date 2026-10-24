"""Repo vs live site: does the repository look like the thing that is running at the live link?

Plain code, no model. It only compares coarse facts (which stack the live page shows, which stack the repo's dependency
files and file names show). It is evidence for a judge, never a verdict, and it is careful to say nothing when it
cannot see enough: a static build of a React app has no framework mark, so "no mark" is never a mismatch.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

# What a live page gives away, found in its HTML. (Only strong marks: a weak one would cause false alarms.)
LIVE_MARKS: Mapping[str, tuple[str, ...]] = {
    "next": ("/_next/static", "__next_data__", 'id="__next"'),
    "nuxt": ("/_nuxt/", "__nuxt__", 'id="__nuxt"'),
    "angular": ("ng-version=", "<app-root"),
    "svelte": ("svelte-", "/_app/immutable"),
    "streamlit": ("streamlit",),
    "gradio": ("gradio-app", "gradio_config"),
    "wordpress": ("/wp-content/", "/wp-includes/"),
}
# Sites made in a no-code builder carry no repository code at all.
BUILDER_MARKS: Mapping[str, tuple[str, ...]] = {
    "Wix": ("static.wixstatic.com", "wix.com/"),
    "Squarespace": ("squarespace.com", "static1.squarespace"),
    "Webflow": ("webflow.com", "data-wf-page"),
    "Framer": ("framer.com", "framerusercontent.com"),
}

# Names in a repo's dependency files that accept a live mark.
ACCEPTS: Mapping[str, tuple[str, ...]] = {
    "next": ("next",),
    "nuxt": ("nuxt", "nuxt3"),
    "angular": ("@angular/core",),
    "svelte": ("svelte", "@sveltejs/kit"),
    "streamlit": ("streamlit",),
    "gradio": ("gradio",),
}
CODE_LANGUAGES = {
    "javascript", "typescript", "python", "go", "java", "kotlin", "c", "c++", "c#", "rust", "ruby", "php", "swift",
    "dart", "scala", "vue", "svelte", "jupyter notebook", "shell", "elixir", "r",
}
NAMES_MENTIONED_IN_FILES = {"next": ("next.config",), "nuxt": ("nuxt.config",), "angular": ("angular.json",),
                            "svelte": ("svelte.config",)}


@dataclass(frozen=True)
class Finding:
    flag_type: str
    level: str      # info or review: this check alone is never "strong"
    reason: str
    evidence: dict


def live_marks(html: str) -> list[str]:
    """Which stacks the live page's HTML shows (empty when it shows none: that is normal and says nothing)."""
    low = (html or "").lower()
    return [name for name, marks in LIVE_MARKS.items() if any(m in low for m in marks)]


def builder_marks(html: str) -> list[str]:
    low = (html or "").lower()
    return [name for name, marks in BUILDER_MARKS.items() if any(m in low for m in marks)]


def dependency_names(texts: Mapping[str, str]) -> set[str]:
    """Package names found in dependency files (package.json, requirements.txt, pyproject.toml, go.mod ...)."""
    names: set[str] = set()
    for path, text in texts.items():
        base = path.rsplit("/", 1)[-1].lower()
        if base == "package.json":
            try:
                data = json.loads(text)
            except ValueError:
                data = {}
            if isinstance(data, dict):
                for key in ("dependencies", "devDependencies", "peerDependencies"):
                    section = data.get(key)
                    if isinstance(section, dict):
                        names |= {str(n).lower() for n in section}
                continue
        # Any other file (or an unreadable package.json): take words that look like package names.
        names |= {w.lower() for w in re.findall(r"[A-Za-z0-9@][A-Za-z0-9_./@-]{1,}", text)}
    return names


def is_code_language(language: str) -> bool:
    return language.lower() in CODE_LANGUAGES


def compare(
    *,
    files: Sequence[str],
    languages: Mapping[str, int],
    dep_names: set[str],
    deps_read: bool,
    files_complete: bool,
    live_html: str,
) -> list[Finding]:
    """What, if anything, does not fit between the repository and the page that is live."""
    out: list[Finding] = []
    live_loaded = bool(live_html and len(live_html.strip()) > 200)
    lowered_files = [f.lower() for f in files]

    # 1. The repository holds no code at all while a live site is running.
    code_langs = [l for l in languages if is_code_language(l)]
    if files_complete and live_loaded and not code_langs and not any(f.endswith((".html", ".htm")) for f in lowered_files):
        out.append(Finding(
            "repo_live_mismatch", "review",
            "The repository holds no code or web pages, but the live link is a running site. The repository may not be "
            "the one behind it.",
            {"kind": "no_code_in_repo", "file_count": len(files), "languages": sorted(languages)},
        ))
        return out  # nothing more to compare

    # 2. A site made in a no-code builder, claimed with a code repository.
    builders = builder_marks(live_html) if live_loaded else []
    if builders and files_complete and code_langs and not live_marks(live_html):
        out.append(Finding(
            "repo_live_mismatch", "info",
            f"The live site looks like it was made in {builders[0]}, not from the code in the repository.",
            {"kind": "builder", "builder": builders[0]},
        ))

    # 3. The live page shows a stack the repository does not use.
    if live_loaded and (deps_read or files_complete):
        for mark in live_marks(live_html):
            if mark == "wordpress":
                if files_complete and not any(f.endswith(".php") for f in lowered_files):
                    out.append(Finding(
                        "repo_live_mismatch", "review",
                        "The live site is built on WordPress, but the repository has no PHP code.",
                        {"kind": "stack", "live": mark, "repo_has": sorted(code_langs)},
                    ))
                continue
            accepted = ACCEPTS.get(mark, ())
            in_deps = any(a in dep_names for a in accepted)
            in_files = any(any(h in f for f in lowered_files) for h in NAMES_MENTIONED_IN_FILES.get(mark, ()))
            if deps_read and not in_deps and not in_files:
                out.append(Finding(
                    "repo_live_mismatch", "review",
                    f"The live site looks built with {mark.capitalize()}, but the repository's dependency files do not "
                    f"list it. The repository may not be the one behind the live link.",
                    {"kind": "stack", "live": mark, "dependency_files_read": True},
                ))
    return out


def first_heading(readme: str) -> Optional[str]:
    """The README's title: the first markdown heading, or the first <h1>."""
    for line in (readme or "").splitlines():
        m = re.match(r"\s*#{1,2}\s+(.+?)\s*#*\s*$", line)
        if m:
            return re.sub(r"[`*_\[\]]", "", m.group(1)).strip()[:120] or None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", readme or "", re.I | re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()[:120] or None
    return None
