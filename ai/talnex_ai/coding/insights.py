"""Profile insights: plain-words readings of the coding signals already saved, each marked strength, neutral or "worth a
look" (evidence.tone) with a one-line evidence.summary.

Evidence beside the score, never subtracted from it: a quiet or irregular account is never a mark against anyone, since
much real work is private (architecture section 18). Built in plain code from saved data, so it costs nothing and is the
same every time. Thresholds come from settings (InsightSettings).
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from talnex_ai.settings import InsightSettings

LANGUAGE_WORDS = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript", "java": "Java", "kotlin": "Kotlin",
    "golang": "Go", "rust": "Rust", "c++": "C++", "c#": "C#", "php": "PHP", "ruby": "Ruby", "swift": "Swift",
    "dart": "Dart", "scala": "Scala",
}


def _insight(kind: str, tone: str, summary: str, **facts: Any) -> dict[str, Any]:
    return {"site": facts.pop("site", "profile"), "signal": kind, "weight": "not_suspicious",
            "evidence": {"tone": tone, "summary": summary, **{k: v for k, v in facts.items() if v is not None}}}


def activity(github: Mapping[str, Any], cfg: InsightSettings) -> Optional[dict]:
    """Active, slowing or quiet over the last months, from the GitHub months (oldest first)."""
    months = [m for m in github.get("months") or [] if isinstance(m, Mapping)]
    if len(months) < 6:
        return None
    counts = [int(m.get("commits") or 0) for m in months]
    trailing_quiet = 0
    for c in reversed(counts):
        if c:
            break
        trailing_quiet += 1
    last_active = next((m["month"] for m in reversed(months) if m.get("commits")), None)
    recent, before = sum(counts[-3:]), sum(counts[-6:-3])
    if trailing_quiet >= cfg.quiet_months:
        return _insight("activity_trend", "look", f"No public commits in the last {trailing_quiet} months"
                        + (f" (last active {last_active})." if last_active else "."), site="github",
                        quiet_months=trailing_quiet, last_active=last_active)
    if before and recent < before * cfg.slowing_share:
        return _insight("activity_trend", "neutral", f"Public activity slowed: {recent} commits in the last 3 months "
                        f"against {before} in the 3 before.", site="github", last_active=last_active)
    return _insight("activity_trend", "strength", f"Active recently: {recent} public commits in the last 3 months.",
                    site="github", last_active=last_active)


def consistency(github: Mapping[str, Any], cfg: InsightSettings) -> Optional[dict]:
    active, gap = github.get("active_months"), github.get("longest_quiet_months")
    if not isinstance(active, int):
        return None
    tone = "strength" if active >= cfg.consistent_months else "look" if active <= cfg.sparse_months else "neutral"
    return _insight("consistency", tone, f"Active in {active} of the last 12 months; the longest quiet stretch was "
                    f"{gap or 0} months.", site="github", active_months=active, longest_gap=gap)


def collaboration(github: Mapping[str, Any], cfg: InsightSettings) -> Optional[dict]:
    prs = github.get("external_prs")
    if not isinstance(prs, int):
        return None
    tone = "strength" if prs >= cfg.collab_prs else "neutral"
    return _insight("collaboration", tone, f"{prs} pull requests opened on other people's public repos.", site="github",
                    external_prs=prs)


def recognition(github: Mapping[str, Any], cfg: InsightSettings) -> Optional[dict]:
    stars = github.get("stars")
    if not isinstance(stars, int):
        return None
    top = github.get("most_starred")
    tone = "strength" if stars >= cfg.stars_strength else "neutral"
    return _insight("recognition", tone, f"{stars} stars across original repos" + (
        f"; most on {top} ({github.get('most_starred_stars')})." if top and stars else "."), site="github", stars=stars)


def rating_trend(site: str, ratings: Iterable[Any], cfg: InsightSettings) -> Optional[dict]:
    points = [int(r) for r in ratings or [] if isinstance(r, (int, float))]
    if len(points) < 3:
        return None
    change = points[-1] - points[0]
    if change >= cfg.rating_points:
        tone, word = "strength", "rising"
    elif change <= -cfg.rating_points:
        tone, word = "look", "falling"
    else:
        tone, word = "neutral", "flat"
    return _insight("rating_trend", tone, f"{site.capitalize()} rating {word} over the last {len(points)} contests: "
                    f"{points[0]} to {points[-1]} ({change:+d}).", site=site, ratings=points)


def problem_mix(leetcode: Mapping[str, Any], cfg: InsightSettings) -> Optional[dict]:
    easy, medium, hard = (int(leetcode.get(k) or 0) for k in ("solved_easy", "solved_medium", "solved_hard"))
    total = easy + medium + hard
    if total < cfg.min_solved:
        return None
    share = lambda n: round(100 * n / total)  # noqa: E731
    if easy / total >= cfg.easy_share:
        tone = "look"
    elif hard / total >= cfg.hard_share and medium / total >= 0.35:
        tone = "strength"
    else:
        tone = "neutral"
    return _insight("problem_mix", tone, f"LeetCode problems solved: {share(easy)}% easy, {share(medium)}% medium, "
                    f"{share(hard)}% hard ({total} in all).", site="leetcode", easy=easy, medium=medium, hard=hard)


def resume_languages(projects: Iterable[Mapping[str, Any]], github: Mapping[str, Any]) -> Optional[dict]:
    """Languages named on the resume projects that no original public repo is written in."""
    text = " ".join(" ".join([p.get("name") or ""] + [f.get("text") or "" for f in p.get("features") or []])
                    for p in projects).lower()
    named = {label for word, label in LANGUAGE_WORDS.items() if re.search(rf"(?<![\w+#]){re.escape(word)}(?![\w+#])", text)}
    langs = {k for k in (github.get("languages") or {})}
    if not named or not langs:
        return None
    missing = sorted(named - langs)
    if not missing:
        return _insight("resume_vs_github", "strength", "Every language named on the resume projects shows up in their "
                        "public repos.", site="github", named=sorted(named))
    return _insight("resume_vs_github", "look", "Named on the resume but in no original public repo: "
                    + ", ".join(missing) + ". The work may be private; worth asking.", site="github", missing=missing)


def build_insights(signals: Iterable[Mapping[str, Any]], projects: Iterable[Mapping[str, Any]],
                   cfg: InsightSettings) -> list[dict]:
    by = {(s.get("site"), s.get("signal")): s.get("evidence") or {} for s in signals}
    github = next((e for (site, _), e in by.items() if site == "github"), {})
    leetcode = by.get(("leetcode", "leetcode_profile"), {})
    codeforces = next((e for (site, _), e in by.items() if site == "codeforces" and "rating" in e), {})
    out = [
        activity(github, cfg), consistency(github, cfg), collaboration(github, cfg), recognition(github, cfg),
        rating_trend("leetcode", leetcode.get("recent_ratings") or [], cfg),
        rating_trend("codeforces", codeforces.get("recent_ratings") or [], cfg),
        problem_mix(leetcode, cfg), resume_languages(list(projects), github),
    ]
    return [i for i in out if i]

