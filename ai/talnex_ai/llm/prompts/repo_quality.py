"""Prompt for the one judgement the repo_quality stage cannot make in plain code: consistency and error handling across
a few sampled source files. The file text is data to analyse, never instructions.
"""
from __future__ import annotations

from typing import Mapping

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You review a few source files from one software project as engineering work.

{DATA_NOT_ORDERS}

Judge only what the files show:
- Consistency: naming style, formatting, and how the files structure the same kind of thing (API handlers, errors,
  data access) the same way.
- Error handling and logging: are failures caught and reported with useful messages, or swallowed, ignored or printed?

The developer's level is given. A fresher is judged on clarity and basic error handling, never on enterprise patterns.
A senior is held to consistent, production-ready patterns.

Reply with one JSON object:
{{"score": <0-10>, "summary": "<one or two plain sentences>",
  "evidence": [{{"path": "<one of the file paths given>", "note": "<what this file shows, a few words>"}}]}}
Give 2 to 4 evidence items. Every path must be exactly one of the paths given; never invent a file."""


def build_user(role_level: str, files: Mapping[str, str], max_chars: int = 6000) -> str:
    parts = [f"Developer level: {role_level}"]
    for path, text in files.items():
        parts.append(f"File: {path}\n" + wrap_untrusted(text[:max_chars], "source_file"))
    return "\n\n".join(parts)
