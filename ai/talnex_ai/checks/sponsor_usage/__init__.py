"""Is an event's sponsor tool really used by the project? (architecture sections 12 and 17). Pure functions.

Two things are known before this runs: whether the tool is listed in a dependency file (Go stage `sponsor_files`)
and the project's file names. This module picks which code files are worth reading, finds the lines that use the
tool, and decides the flag. A mention in the README alone does not count as use.

"Used" here means: the tool's name appears in a source file the team wrote, outside tests and configuration, on a line
that is not just an import. That is a plain-text check, so a tool called under another name (a bare web address, say)
can be missed; when we could not read every code file, the flag is capped at "review" instead of "strong".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Optional, Sequence

SOURCE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".go", ".java", ".kt", ".rb", ".php", ".rs", ".dart",
    ".cs", ".swift", ".vue", ".svelte",
}
_SKIPPED_FOLDERS = {
    "node_modules", "vendor", "dist", "build", ".next", "out", "target", "__pycache__", ".venv", "venv", "coverage",
    "test", "tests", "__tests__", "spec", "specs", "e2e", "cypress", "docs", "examples", "example",
}
MAX_CODE_FILES = 40

_IMPORT = re.compile(r"^\s*(import\b|from\s+\S+\s+import\b|const\s+.*=\s*require\(|require\(|using\s|#include\b|package\b)")
_COMMENT = re.compile(r"^\s*(//|#|\*|/\*|<!--)")


@dataclass(frozen=True)
class Use:
    file: str
    line: int
    text: str


def candidate_source_files(files: Iterable[str], limit: int = MAX_CODE_FILES) -> list[str]:
    """The team's source files worth reading: the shallowest first, since the main code is near the top."""
    keep = []
    for f in files:
        p = PurePosixPath(f)
        if p.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        parts = {s.lower() for s in p.parent.parts}
        name = p.name.lower()
        if parts & _SKIPPED_FOLDERS or ".test." in name or ".spec." in name or name.startswith("test_") or name.endswith("_test.go"):
            continue
        if re.search(r"(^|\.)(config|conf)\.[a-z]+$", name) or name.endswith(".min.js"):
            continue
        keep.append(f)
    keep.sort(key=lambda f: (len(PurePosixPath(f).parts), f))
    return keep[:limit]


def _name_pattern(tool: str) -> Optional[re.Pattern]:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", tool) if w]
    if not words or len("".join(words)) < 3:
        return None
    return re.compile(r"[\s\-_.@/]*".join(re.escape(w) for w in words), re.IGNORECASE)


def find_uses(tool: str, texts: Mapping[str, str], per_file: int = 2) -> list[Use]:
    """Lines that use the tool: not an import, not a comment. A few examples per file are enough as evidence."""
    pattern = _name_pattern(tool)
    if pattern is None:
        return []
    uses: list[Use] = []
    for path, text in texts.items():
        found = 0
        for number, line in enumerate(text.splitlines(), start=1):
            if _COMMENT.match(line) or _IMPORT.match(line) or not pattern.search(line):
                continue
            uses.append(Use(path, number, line.strip()[:160]))
            found += 1
            if found == per_file:
                break
    return uses


def mentioned(tool: str, text: str) -> bool:
    pattern = _name_pattern(tool)
    return bool(pattern and pattern.search(text or ""))


@dataclass(frozen=True)
class SponsorVerdict:
    tool: str
    listed: bool
    used: bool
    in_readme: bool
    level: Optional[str]   # None = nothing to flag
    reason: str = ""


def decide(tool: str, *, listed: bool, used: bool, in_readme: bool, partial: bool) -> SponsorVerdict:
    """The flag for one sponsor tool (architecture section 17).

    Listed and used: fine. Used but not listed: fine (it may be called over plain HTTP). Listed only, or README only:
    review. Neither: strong, but only review when we could not read all the code."""
    if used:
        return SponsorVerdict(tool, listed, used, in_readme, None)
    if listed:
        return SponsorVerdict(tool, listed, used, in_readme, "review",
                              f"{tool} is listed in a dependency file, but no call to it was found in the code we read")
    if in_readme:
        return SponsorVerdict(tool, listed, used, in_readme, "review",
                              f"{tool} is mentioned in the README, but it is in no dependency file and no call to it was found")
    level = "review" if partial else "strong"
    return SponsorVerdict(tool, listed, used, in_readme, level,
                          f"{tool} is in no dependency file, not in the code we read, and not in the README")
