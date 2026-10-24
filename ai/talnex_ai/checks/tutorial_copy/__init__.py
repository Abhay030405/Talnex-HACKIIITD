"""Tutorial copy: search the web for the project as a known tutorial, then let a model judge README against the hits.

The search is the evidence. With no search result there is nothing to judge, so no flag. The answer is a possible match
for a human to look at (Info for a similar idea, Review for a close match), never a verdict and never Strong.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence
from urllib.parse import urlparse

from talnex_ai.formats import FormatError
from talnex_ai.formats.parse import parse_json_block

MATCHES = ("none", "similar_idea", "close_match")
LEVEL = {"similar_idea": "info", "close_match": "review"}
MAX_HITS = 8


@dataclass(frozen=True)
class Judgement:
    match: str
    matched_url: str
    reason: str


def queries(repo_name: str, readme_title: Optional[str]) -> list[str]:
    """Up to two searches: the README title as a tutorial, and the repository name as a known project."""
    out = []
    if readme_title:
        out.append(f'"{readme_title}" tutorial step by step github')
    if repo_name and repo_name.lower() != (readme_title or "").lower():
        out.append(f'"{repo_name}" tutorial source code')
    return out[:2]


def _host(url: str) -> str:
    return (urlparse(url if "//" in url else "https://" + url).hostname or "").lower()


def drop_own_pages(hits: Sequence, repo: str, live_host: str) -> list:
    """Results that are the project's own repository or live site are not evidence of copying."""
    own_repo = f"github.com/{repo}".lower()
    kept, seen = [], set()
    for h in hits:
        low = h.url.lower().rstrip("/")
        if own_repo and own_repo in low:
            continue
        if live_host and _host(h.url) == live_host:
            continue
        if low in seen:
            continue
        seen.add(low)
        kept.append(h)
    return kept[:MAX_HITS]


def parse_judgement(text: str, allowed_urls: Sequence[str]) -> Judgement:
    data = parse_json_block(text)
    if not isinstance(data, dict):
        raise FormatError("the answer must be one JSON object")
    match = str(data.get("match", "")).strip().lower()
    if match not in MATCHES:
        raise FormatError(f'"match" must be one of {", ".join(MATCHES)}')
    url = str(data.get("matched_url") or "").strip()
    reason = str(data.get("reason") or "").strip()[:300]
    # Evidence rule: a match must point at a search result we really got. Otherwise it counts as no match.
    allowed = {u.lower().rstrip("/") for u in allowed_urls}
    if match != "none" and url.lower().rstrip("/") not in allowed:
        return Judgement("none", "", "the model named no search result as the source")
    return Judgement(match, url if match != "none" else "", reason)


def flag_for(j: Judgement) -> Optional[tuple[str, str, dict]]:
    """(level, reason, evidence) for a judgement, or None when there is nothing to flag."""
    level = LEVEL.get(j.match)
    if level is None:
        return None
    what = "closely matches" if j.match == "close_match" else "has a similar idea to"
    reason = f"Possible tutorial match (not a verdict): the project may be built from a public tutorial. Its README {what} {j.matched_url}."
    if j.reason:
        reason += f" {j.reason}"
    return level, reason, {"matched_url": j.matched_url, "match": j.match, "model_reason": j.reason}
