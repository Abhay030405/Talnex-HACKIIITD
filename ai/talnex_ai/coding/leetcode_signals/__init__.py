"""Stage `leetcode` (recruiter, candidate-level): public LeetCode profile facts. Evidence only, never a verdict.

This is the public-page half only: solved counts, contest rating, recent activity. The logged-in Code Replay capture and
paste analysis are not built (see `coding/leetcode_capture/`). Running it twice replaces the row.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.coding.profile import first_number, run_profile
from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, stage

SITE = "leetcode"
SIGNAL = "leetcode_profile"
FIELDS = {
    "solved_total": "total problems solved", "solved_easy": "easy problems solved", "solved_medium": "medium problems solved",
    "solved_hard": "hard problems solved", "contest_rating": "contest rating", "contests_attended": "contests attended",
    "global_ranking": "global ranking", "submissions_past_year": "submissions in the past year",
    "active_days": "total active days", "max_streak": "max streak in days",
}


def profile_url(handle: str) -> str:
    return f"https://leetcode.com/u/{handle}/"


def _solved(word: str, text: str):
    return first_number([rf"\b{word}\b[:\s]*(\d+)\s*/\s*\d+", rf"\b{word}\b[:\s]+(\d+)\b"], text)


def parse_profile(text: str) -> dict[str, Any]:
    """Plain-code reading of the fetched page text. Returns only what it can see; {} if the layout is not recognised."""
    facts = {
        "solved_total": first_number([r"\bSolved\b[:\s]*(\d+)\s*/\s*\d+", r"(\d+)\s*/\s*\d+\s*\n?\s*Solved\b",
                                      r"Total Solved[:\s]*(\d+)"], text),
        "solved_easy": _solved("Easy", text), "solved_medium": _solved("Med(?:ium)?", text), "solved_hard": _solved("Hard", text),
        "contest_rating": first_number([r"Contest Rating[:\s]*([\d,]+(?:\.\d+)?)"], text, as_float=True),
        "contests_attended": first_number([r"Attended[:\s]*(\d+)", r"Contests? Attended[:\s]*(\d+)"], text),
        "global_ranking": first_number([r"Global Ranking[:\s]*([\d,]+)"], text),
        "submissions_past_year": first_number([r"([\d,]+)\s+submissions? in the past one year"], text),
        "active_days": first_number([r"Total Active Days[:\s]*(\d+)"], text),
        "max_streak": first_number([r"Max Streak[:\s]*(\d+)"], text),
    }
    if facts["contest_rating"] is not None and facts["contest_rating"] == int(facts["contest_rating"]):
        facts["contest_rating"] = int(facts["contest_rating"])
    keep = {k: v for k, v in facts.items() if v is not None}
    return keep if {"solved_total", "solved_easy", "solved_medium", "solved_hard", "contest_rating", "submissions_past_year"} & keep.keys() else {}


@stage("leetcode")
def leetcode(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    return run_profile(job, ctx, site=SITE, signal=SIGNAL, url_for=profile_url, parse=parse_profile, fields=FIELDS)
