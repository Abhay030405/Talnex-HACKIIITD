"""Clone a repo inside a VM and read the files that decide how it runs.

The clone happens inside the throwaway VM, so the repo's code never touches the machine that runs TalNex. Only public
GitHub repositories are cloned; a private or missing one ends as "could not run: repo not reachable", never "broken".
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional, Protocol

from talnex_ai.sandbox.client import ExecResult
from talnex_ai.sandbox.stack_detect.detect import ENTRY_NAMES, MANIFESTS, RepoFacts, candidate_dirs

REPO_DIR = "/work/repo"
MAX_FILES = 3000
MAX_FILE_BYTES = 20_000
MAX_README_BYTES = 30_000
GITHUB_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./@+=-]+$")
_MARK = "@@@TALNEX-FILE "


class VmLike(Protocol):
    def exec(self, command: str, **kwargs) -> ExecResult: ...


class RepoUnreachable(RuntimeError):
    """The repository could not be cloned: private, missing, not on GitHub, or the network failed."""


def clean_github_url(raw: str) -> Optional[str]:
    """`https://github.com/owner/name` from what a person typed (www, .git, trailing slash, subpaths), or None."""
    raw = (raw or "").strip()
    if raw and "://" not in raw:
        raw = "https://" + raw
    m = re.match(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", raw)
    if not m:
        return None
    name = m.group(2)[:-4] if m.group(2).endswith(".git") else m.group(2)
    return f"https://github.com/{m.group(1)}/{name}" if name else None


def clone(vm: VmLike, url: str, *, timeout_seconds: int = 240) -> None:
    """Shallow-clone the default branch into REPO_DIR. Raises RepoUnreachable with a plain reason."""
    clean = clean_github_url(url)
    if clean is None or not GITHUB_URL.match(clean):
        raise RepoUnreachable("the repository link is not a GitHub address")
    res = vm.exec(f"rm -rf {REPO_DIR} && GIT_TERMINAL_PROMPT=0 git clone --depth 1 --quiet {shlex.quote(clean)} {REPO_DIR}",
                  timeout_seconds=timeout_seconds)
    if res.ok:
        return
    text = res.output.lower()
    if res.timed_out:
        raise RepoUnreachable("cloning the repository took too long")
    if "not found" in text or "could not read username" in text or "authentication" in text or "terminal prompts disabled" in text:
        raise RepoUnreachable("the repository does not exist or is private")
    raise RepoUnreachable("the repository could not be cloned: " + res.output[-200:].replace("\n", " "))


def paths_to_read(files: list[str]) -> list[str]:
    """The few files worth reading: manifests, entry files, Dockerfile, env example, compose file and the README."""
    wanted: list[str] = []
    present = set(files)
    for d in candidate_dirs(files):
        prefix = f"{d}/" if d else ""
        for name in (*MANIFESTS, "Dockerfile", ".env.example", ".env.sample", ".env.template"):
            if prefix + name in present:
                wanted.append(prefix + name)
        for sub in ("", "app/", "src/", "api/"):
            for name in ENTRY_NAMES:
                if prefix + sub + name in present:
                    wanted.append(prefix + sub + name)
    for name in ("README.md", "readme.md", "README", "Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".env.example"):
        if name in present:
            wanted.append(name)
    seen: set[str] = set()
    return [p for p in wanted if _SAFE_PATH.match(p) and not (p in seen or seen.add(p))]


def read_files(vm: VmLike, paths: list[str], *, max_bytes: int = MAX_FILE_BYTES) -> dict[str, str]:
    """Read some files of the cloned repo in one go. Paths with odd characters are skipped (they are never shell-quoted
    into a command we did not write)."""
    safe = [p for p in paths if _SAFE_PATH.match(p)]
    if not safe:
        return {}
    script = "; ".join(
        f'echo "{_MARK}{p}"; head -c {MAX_README_BYTES if PurePosixPath(p).name.lower().startswith("readme") else max_bytes} {shlex.quote(p)}; echo'
        for p in safe
    )
    res = vm.exec(f"cd {REPO_DIR} && ({script})", timeout_seconds=90)
    return parse_file_dump(res.stdout)


def read_facts(vm: VmLike) -> RepoFacts:
    """Read the file list and the key files from the cloned repo."""
    listing = vm.exec(f"cd {REPO_DIR} && git ls-files | head -n {MAX_FILES}", timeout_seconds=60)
    files = [f for f in listing.stdout.splitlines() if f]
    return RepoFacts(files=files, texts=read_files(vm, paths_to_read(files)))


def parse_file_dump(dump: str) -> dict[str, str]:
    """Split the output of the read script back into {path: text}."""
    out: dict[str, str] = {}
    current: Optional[str] = None
    lines: list[str] = []
    for line in dump.split("\n"):
        if line.startswith(_MARK):
            if current is not None:
                out[current] = "\n".join(lines).rstrip("\n")
            current, lines = line[len(_MARK):].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        out[current] = "\n".join(lines).rstrip("\n")
    return out


@dataclass(frozen=True)
class Cloned:
    url: str
    facts: RepoFacts
