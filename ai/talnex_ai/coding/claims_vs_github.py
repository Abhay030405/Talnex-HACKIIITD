"""Resume claims against GitHub: when the resume says a project was built, by whom and for how long, set beside what the
repository's history shows. Plain code, evidence only, never scored (tone strength / neutral / look like insights.py).

Claimed dates and team words are read from the resume text near the project (claimed_from_text) and are never guessed: a
model's answer is kept only when the text supports it.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from talnex_ai.settings import InsightSettings

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_POINT = rf"(?:{_MON}\s*'?(\d{{2,4}})|(\d{{1,2}})[/.-](\d{{4}})|(\d{{4}})[/.-](\d{{1,2}})\b|(\d{{4}}))"
_RANGE = re.compile(rf"{_POINT}\s*(?:-|–|—|to|until|till)\s*(?:(present|now|current|ongoing)|{_POINT})", re.IGNORECASE)
_SINGLE = re.compile(_POINT, re.IGNORECASE)
_SOLO = re.compile(r"\b(solo|individual(?:ly)?|personal project|by myself|on my own|single[- ]handed)", re.IGNORECASE)
_TEAM = re.compile(r"\b(team|group|collaborat\w*|with \d+ others|co-?built)\b", re.IGNORECASE)
_TEAM_SIZE = re.compile(r"\bteam of (\d{1,2})\b|\b(\d{1,2})[- ](?:member|person|people)\b", re.IGNORECASE)


def _point(groups: tuple) -> Optional[str]:
    """'YYYY-MM' or 'YYYY' from one matched date; None when the year is not plausible."""
    mon, y1, m2, y2, y3, m3, y4 = groups
    if mon:
        year, month = int(y1) + (2000 if len(y1) == 2 else 0), MONTHS[mon.lower()[:3]]
    elif y2:
        year, month = int(y2), int(m2)
    elif y3:
        year, month = int(y3), int(m3)
    else:
        year, month = int(y4), 0
    if not 1990 <= year <= 2100 or month > 12:
        return None
    return f"{year:04d}-{month:02d}" if month else f"{year:04d}"


def parse_dates(text: str) -> tuple[Optional[str], Optional[str]]:
    """The first date range (or single date) in the text: ('2026-01', '2026-03'), ('2025', 'present'), …, or (None, None)."""
    m = _RANGE.search(text or "")
    if m:
        g = m.groups()
        start = _point(g[:7])
        end = "present" if g[7] else _point(g[8:15])
        if start:
            return start, end
    m = _SINGLE.search(text or "")
    if m:
        p = _point(m.groups())
        return p, p
    return None, None


def claimed_from_text(text: str, model: Mapping[str, Any]) -> dict[str, Any]:
    """Claimed dates, team and role for one project. The text decides; the model's answer only fills a gap the text
    supports (its year must appear in the text, its role words must appear in the text)."""
    start, end = parse_dates(text)
    lowered = (text or "").lower()
    if not start and model.get("claimed_start"):
        s = str(model["claimed_start"])
        if s[:4].isdigit() and s[:4] in lowered:
            start, e = str(model["claimed_start"]), str(model.get("claimed_end") or "")
            end = e if e == "present" or (e[:4].isdigit() and e[:4] in lowered) else None
    team = "solo" if _SOLO.search(text or "") else "team" if _TEAM.search(text or "") else None
    size_m = _TEAM_SIZE.search(text or "")
    size = int(next(g for g in size_m.groups() if g)) if size_m else None
    if size and size > 1:
        team = "team"
    role = str(model.get("claimed_role") or "").strip()[:40]
    role = role if role and all(w in lowered for w in re.findall(r"[a-z]+", role.lower())) else None
    return {"start": start, "end": end, "team": team, "team_size": size, "role": role}


def _month_index(value: str, *, end: bool) -> Optional[int]:
    if not value:
        return None
    if value == "present":
        now = datetime.now(timezone.utc)
        return now.year * 12 + now.month - 1
    year = int(value[:4])
    month = int(value[5:7]) if len(value) >= 7 else (12 if end else 1)
    return year * 12 + month - 1


def compare(claimed: Mapping[str, Any], actual: Mapping[str, Any], account: Optional[str],
            cfg: InsightSettings) -> list[dict[str, Any]]:
    """Readings of the claims against the repository history. Each is {signal, evidence:{tone, summary, …}}."""
    out: list[dict[str, Any]] = []

    def add(kind: str, tone: str, summary: str, **facts: Any) -> None:
        out.append({"site": "github", "signal": kind, "weight": "not_suspicious",
                    "evidence": {"tone": tone, "summary": summary, **facts}})

    dates = [d for d in actual.get("commit_dates") or [] if d]
    lo, hi = _month_index(claimed.get("start") or "", end=False), _month_index(claimed.get("end") or claimed.get("start") or "", end=True)
    if lo is not None and hi is not None and dates:
        slack = cfg.date_slack_months
        months = [int(d[:4]) * 12 + int(d[5:7]) - 1 for d in dates]
        outside = sum(1 for m in months if m < lo - slack or m > hi + slack)
        share = outside / len(months)
        rng = f"{claimed.get('start')} to {claimed.get('end') or claimed.get('start')}"
        seen = f"{actual.get('first_commit', '')[:10]} to {actual.get('last_commit', '')[:10]}"
        if share >= cfg.outside_share:
            add("claimed_dates", "look", f"The resume says {rng}, but {outside} of {len(months)} commits fall outside it "
                f"(commits run {seen}).", outside_share=round(share, 2))
        else:
            add("claimed_dates", "strength", f"The resume's dates ({rng}) match the commit history ({seen}).",
                outside_share=round(share, 2))

    people = [c for c in actual.get("contributors") or [] if c.get("commits")]
    total = sum(c["commits"] for c in people)
    shares = [{"login": c["login"], "share": round(c["commits"] / total, 2)} for c in people] if total else []
    mine = next((s for s in shares if account and s["login"].lower() == account.lower()), None)
    who = ", ".join(f"{s['login']} {round(s['share'] * 100)}%" for s in shares[:5])
    others = [s for s in shares if not mine or s["login"].lower() != mine["login"].lower()]
    if claimed.get("team") == "solo" and shares:
        if any(s["share"] >= cfg.solo_other_share for s in others) and len(shares) >= 2:
            add("claimed_team", "look", f"The resume says solo, but the history has {len(shares)} contributors ({who}).",
                contributors=shares)
        else:
            add("claimed_team", "strength", f"The resume says solo and the history agrees ({who}).", contributors=shares)
    elif claimed.get("team") == "team" and shares:
        add("claimed_team", "neutral", f"A team project; commits by {who}.", contributors=shares)
    if shares and not account:
        add("own_share", "neutral", "The candidate's GitHub account is not known, so their share of the commits "
            "cannot be told.", contributors=shares)
    elif mine is not None and mine["share"] < cfg.own_share_min and len(shares) >= 2:
        add("own_share", "look", f"The candidate ({mine['login']}) wrote {round(mine['share'] * 100)}% of the commits "
            f"({who}).", contributors=shares)
    elif mine is not None:
        add("own_share", "strength" if mine["share"] >= 0.5 else "neutral",
            f"The candidate ({mine['login']}) wrote {round(mine['share'] * 100)}% of the commits.", contributors=shares)

    if lo is not None and hi is not None and dates and hi - lo + 1 >= cfg.burst_claimed_months:
        days = Counter(d[:10] for d in dates)
        top = sum(n for _, n in days.most_common(2)) / len(dates)
        if top >= cfg.burst_days_share:
            add("claimed_effort", "look", f"The resume claims {hi - lo + 1} months of work, but {round(top * 100)}% of "
                f"the commits land on {min(2, len(days))} day(s).", busiest_days_share=round(top, 2))
    return out


def github_facts(reader, repo: str, max_pages: int) -> dict[str, Any]:
    """First and last commit, commit count, commit dates (newest pages, capped) and contributors with commit counts."""
    contributors = [{"login": c.get("login") or "?", "commits": int(c.get("contributions") or 0)}
                    for c in reader._get(f"/repos/{repo}/contributors", per_page=30) or []]
    dates: list[str] = []
    for page in range(1, max_pages + 1):
        rows = reader._get(f"/repos/{repo}/commits", per_page=100, page=page) or []
        dates += [((c.get("commit") or {}).get("author") or {}).get("date") or "" for c in rows]
        if len(rows) < 100:
            break
    dates = sorted(d for d in dates if d)
    # ponytail: only the newest max_pages*100 commits are read, so a long history's first commit may be later than the real one
    return {"repo": repo, "commit_count": sum(c["commits"] for c in contributors) or len(dates),
            "first_commit": dates[0] if dates else None, "last_commit": dates[-1] if dates else None,
            "commit_dates": dates, "contributors": contributors}


def add_claims(report: dict, claims_by_project: Mapping[str, Mapping[str, Any]], reader, accounts: Mapping[str, Optional[str]],
               cfg: InsightSettings, max_pages: int, repo_of) -> None:
    """Fill project['claims_vs_github'] and add the readings to report['profile_insights']. A repo GitHub cannot read is
    left out with its reason; nothing here raises."""
    insights = report.setdefault("profile_insights", [])
    for p in report.get("projects") or []:
        claimed = claims_by_project.get(p["id"]) or {}
        repo = repo_of(p.get("repo_url"))
        if not repo or reader is None:
            continue
        try:
            actual = github_facts(reader, repo, max_pages)
        except Exception as err:   # rate limit, private repo, network: could not check, never a mark
            p["claims_vs_github"] = {"claimed": claimed, "actual": None, "insights": [], "reason": str(err)[:160]}
            continue
        found = compare(claimed, actual, accounts.get(p["id"]), cfg)
        for f in found:
            f["evidence"]["project"] = p["name"]
        p["claims_vs_github"] = {"claimed": claimed, "insights": found,
                                 "actual": {k: v for k, v in actual.items() if k != "commit_dates"}}
        insights += found
