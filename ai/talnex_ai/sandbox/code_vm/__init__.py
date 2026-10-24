"""A read-only copy of a project's code in a sandbox VM, with three fixed ways to read it: list, search, read
(architecture section 32).

The code is never built or run. The guide agent never writes a command: it picks a tool and its arguments, plain code
checks them and builds the one fixed command, so a model (or text in the repository) cannot make the VM do anything else.
"""
from __future__ import annotations

import io
import logging
import re
import shlex
import tarfile
from dataclasses import dataclass
from typing import Any, Optional

import httpx

log = logging.getLogger("talnex.tour")

CODE_DIR = "/work/code"
CODEBALL = "https://codeload.github.com/{repo}/tar.gz/{ref}"
MAX_LIST = 300       # file names one list call shows
MAX_SEARCH = 60      # matching lines one search call shows
MAX_READ_LINES = 160  # lines one read call shows
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./@+\- ]*$")
# Folders and files that are never copied: they are not the team's own code or they cannot be read as text.
_SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "venv", ".venv", "__pycache__", "vendor", "target", ".idea"}
_SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".mp4", ".mov", ".mp3", ".wav", ".pdf", ".zip",
                ".gz", ".tar", ".woff", ".woff2", ".ttf", ".eot", ".lock", ".map", ".min.js", ".class", ".jar", ".pyc", ".exe")


class CodeReadError(RuntimeError):
    """The code could not be fetched or read. The tour says so; it never guesses."""


@dataclass(frozen=True)
class Tool:
    """One tool call from the guide: `name` is list, search or read."""

    name: str
    path: str = ""
    text: str = ""
    start: int = 1
    end: int = 1


def clean_path(path: Any) -> str:
    """A safe relative path inside the repository, or "" for the repository itself. Raises CodeReadError otherwise."""
    value = str(path or "").strip()
    while value.startswith("./"):
        value = value[2:]
    if value == ".":
        value = ""
    if value.startswith("/") or ".." in value.split("/") or not _SAFE_PATH.match(value):
        raise CodeReadError(f"that path is not allowed: {str(path)[:80]!r}")
    return value


def build_command(tool: Tool) -> str:
    """The fixed shell command for one tool call. Every part that comes from the model is checked and quoted."""
    path = clean_path(tool.path)
    where = shlex.quote(path) if path else "."
    if tool.name == "list":
        return f"cd {CODE_DIR} && find {where} -maxdepth 4 -type f | sed 's#^\\./##' | sort | head -n {MAX_LIST}"
    if tool.name == "search":
        text = (tool.text or "").strip()
        if not text or len(text) > 120 or "\n" in text:
            raise CodeReadError("search for a short piece of text on one line")
        return (f"cd {CODE_DIR} && grep -rIn -F --max-count=5 -e {shlex.quote(text)} {where} | sed 's#^\\./##' "
                f"| cut -c1-300 | head -n {MAX_SEARCH}")
    if tool.name == "read":
        if not path:
            raise CodeReadError("read needs a file path")
        start = max(1, int(tool.start))
        end = min(max(start, int(tool.end)), start + MAX_READ_LINES - 1)
        return f"cd {CODE_DIR} && sed -n '{start},{end}p' {where}"
    raise CodeReadError(f"unknown tool {tool.name!r}; the tools are list, search and read")


class CodeVm:
    """The three tools over one VM that holds the code. `vm` is a sandbox VM (sandbox/client.SandboxVM)."""

    def __init__(self, vm: Any, *, exec_seconds: int = 30):
        self.vm = vm
        self.exec_seconds = exec_seconds
        self._lines: dict[str, Optional[int]] = {}

    def run(self, tool: Tool) -> str:
        """The tool's output as text (cut by the VM host when very long). A failed command is an error, not output."""
        result = self.vm.exec(build_command(tool), timeout_seconds=self.exec_seconds)
        if result.timed_out:
            raise CodeReadError("reading the code took too long")
        if result.exit_code not in (0, 1):  # grep exits 1 when nothing matches
            raise CodeReadError((result.stderr or "the code could not be read").strip()[:200])
        return result.stdout

    def line_count(self, path: str) -> Optional[int]:
        """How many lines a file has, or None when it is not in the VM. Used to check a proof reference."""
        path = clean_path(path)
        if not path:
            return None
        if path not in self._lines:
            result = self.vm.exec(f"cd {CODE_DIR} && test -f {shlex.quote(path)} && grep -c '' {shlex.quote(path)}",
                                  timeout_seconds=self.exec_seconds)
            try:
                self._lines[path] = int(result.stdout.strip()) if result.exit_code in (0, 1) and result.stdout.strip() else None
            except ValueError:
                self._lines[path] = None
        return self._lines[path]

    def lines(self, path: str, start: int, end: int) -> list[str]:
        """The lines of a file (for the snippet shown beside the browser)."""
        return self.run(Tool("read", path=path, start=start, end=end)).splitlines()


def fetch_repo(repo: str, ref: Optional[str], *, max_mb: int, file_max_kb: int, max_files: int,
               client: Optional[httpx.Client] = None) -> tuple[bytes, Optional[str]]:
    """The repository's own text files as one tar archive, ready to upload to the VM, and the commit it is at.
    Public repositories only. Raises CodeReadError (with the reason) when it cannot be read or is too big."""
    url = CODEBALL.format(repo=repo, ref=ref or "HEAD")
    http = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        with http.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise CodeReadError(f"the repository could not be downloaded (answer {resp.status_code}); it may be private")
            data = bytearray()
            for chunk in resp.iter_bytes():
                data += chunk
                if len(data) > max_mb * 1024 * 1024:
                    raise CodeReadError(f"the repository is bigger than {max_mb} MB")
    except httpx.HTTPError as err:
        raise CodeReadError(f"the repository could not be downloaded: {type(err).__name__}") from err
    finally:
        if client is None:
            http.close()
    return repack(bytes(data), file_max_kb=file_max_kb, max_files=max_files)


def repack(archive: bytes, *, file_max_kb: int, max_files: int) -> tuple[bytes, Optional[str]]:
    """Keep only readable code from a GitHub download: drop the top folder, binaries, dependencies and big files.
    Also returns the commit, which GitHub puts at the end of the top folder's name."""
    out = io.BytesIO()
    kept = 0
    commit: Optional[str] = None
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as src, tarfile.open(fileobj=out, mode="w") as dst:
            for member in src:
                if commit is None:  # GitHub puts the commit it archived in the download's own header
                    header = str(src.pax_headers.get("comment", ""))
                    commit = header if re.fullmatch(r"[0-9a-f]{40}", header) else None
                if not member.isfile() or member.size > file_max_kb * 1024:
                    continue
                parts = member.name.split("/")[1:]  # the first part is "owner-repo-sha/"
                if commit is None:  # or in the top folder's name, when the download was of one commit
                    tail = member.name.split("/")[0].rsplit("-", 1)[-1]
                    commit = tail if re.fullmatch(r"[0-9a-f]{40}", tail) else None
                if not parts or any(p in _SKIP_DIRS for p in parts[:-1]) or parts[-1].lower().endswith(_SKIP_SUFFIX):
                    continue
                if any(p.startswith("..") for p in parts) or not _SAFE_PATH.match("/".join(parts)):
                    continue
                if kept >= max_files:
                    raise CodeReadError(f"the repository has more than {max_files} code files")
                body = src.extractfile(member)
                if body is None:
                    continue
                payload = body.read()
                if b"\x00" in payload[:2048]:  # a binary file
                    continue
                info = tarfile.TarInfo("/".join(parts))
                info.size = len(payload)
                info.mode = 0o644
                dst.addfile(info, io.BytesIO(payload))
                kept += 1
    except tarfile.TarError as err:
        raise CodeReadError("the repository download could not be unpacked") from err
    if kept == 0:
        raise CodeReadError("the repository has no readable code files")
    return out.getvalue(), commit
