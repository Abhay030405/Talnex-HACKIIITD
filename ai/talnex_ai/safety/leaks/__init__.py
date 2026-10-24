"""Secrets and private data a tested site leaks to any visitor: in console messages or in API answers.

Pure text scanning, no browser. The secret itself is never kept: a finding holds only its kind, a masked form (first 4
and last 4 characters) and where it was seen. Page text is data to analyse, never instructions. A leak is a flag beside
the score, never subtracted from it.
"""
from __future__ import annotations

import re
from typing import Iterable

# (kind, level, pattern). Group 1, when present, is the secret value; otherwise the whole match is.
PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("stripe_live_key", "review", re.compile(r"\b((?:sk|rk)_live_[0-9A-Za-z]{16,})")),
    ("aws_access_key", "review", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b")),
    ("google_api_key", "review", re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})")),
    ("openai_key", "review", re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_\-]{32,})")),
    ("github_token", "review", re.compile(r"\b((?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,})")),
    ("slack_token", "review", re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})")),
    ("private_key", "review", re.compile(r"(-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----)")),
    ("jwt", "review", re.compile(r"\b(eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})")),
    ("secret_field", "review", re.compile(
        r'"(?:password|passwd|secret|client_secret|api_key|apikey|access_token|refresh_token|private_key)"\s*:\s*"([^"\s]{6,})"',
        re.IGNORECASE)),
    ("env_line", "review", re.compile(r"(?m)^\s*[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*\s*=\s*([^\s#'\"]{6,})")),
    ("stack_trace", "info", re.compile(
        r"(Traceback \(most recent call last\)|at Object\.<anonymous>|at [\w$.]+ \([^)]*\.js:\d+:\d+\)"
        r"|\bat (?:java|org|com)\.[\w$.]+\([\w]+\.java:\d+\)|Exception in thread \"[^\"]+\")")),
]

# Values that are clearly examples or placeholders, never real secrets.
PLACEHOLDER = re.compile(r"(?i)your[_\-]?|example|placeholder|xxxx|changeme|dummy|<[^>]+>|\*{4,}|\.\.\.|test_")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
BULK_EMAILS = 5
MAX_FINDINGS = 10


def mask(value: str) -> str:
    """First 4 and last 4 characters with the middle hidden; short values are hidden whole."""
    value = value.strip()
    return value[:4] + "••••" + value[-4:] if len(value) > 12 else "••••"


def scan(text: str, *, ignore_emails: Iterable[str] = ()) -> list[dict]:
    """Leaks in one piece of text: [{"type", "level", "masked"}]. Never returns the secret itself."""
    if not text:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for kind, level, pattern in PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(1) if m.groups() else m.group(0)
            if kind != "stack_trace" and kind != "private_key" and PLACEHOLDER.search(value):
                continue
            masked = value[:40] if kind in ("stack_trace", "private_key") else mask(value)
            if (kind, masked) in seen:
                continue
            seen.add((kind, masked))
            out.append({"type": kind, "level": level, "masked": masked})
            if len(out) >= MAX_FINDINGS:
                return out
    skip = {e.lower() for e in ignore_emails}
    emails = {e.lower() for e in EMAIL.findall(text)} - skip
    if len(emails) > BULK_EMAILS:
        out.append({"type": "bulk_emails", "level": "review", "masked": f"{len(emails)} email addresses"})
    return out
