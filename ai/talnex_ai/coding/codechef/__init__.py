"""Stage `codechef` (recruiter, candidate-level): public CodeChef profile facts. Evidence only, never a verdict.

CodeChef shows no public plagiarism page that we can read, so this keeps only what the public profile shows: rating,
stars, ranks, contests, problems solved. Running it twice replaces the row.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.coding.profile import first_number, run_profile
from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, stage

SITE = "codechef"
SIGNAL = "codechef_profile"
FIELDS = {
    "rating": "current contest rating", "stars": "number of stars (1 to 7)", "highest_rating": "highest rating",
    "global_rank": "global rank", "country_rank": "country rank",
    "contests_participated": "contests taken part in", "problems_solved": "total problems solved",
}


def profile_url(handle: str) -> str:
    return f"https://www.codechef.com/users/{handle}"


def parse_profile(text: str) -> dict[str, Any]:
    """Plain-code reading of the fetched page text. Returns only what it can see; {} if the layout is not recognised."""
    facts = {
        "rating": first_number([r"(\d{3,4})\s*\**\s*\n?\s*(?:\(?\d\s*★\)?\s*)?(?:CodeChef\s+)?(?:Contest\s+)?Rating\b(?!\s*[:#]?\s*\d)",
                                r"(?<!Highest )(?<!Highest\s)\bRating[:\s]+(\d{3,4})\b"], text),
        "stars": first_number([r"(\d)\s*★", r"(\d)\s*[- ]?stars?\b"], text),
        "highest_rating": first_number([r"Highest Rating[:\s(]*(\d{3,4})", r"\(Highest Rating\s*(\d{3,4})\)"], text),
        "global_rank": first_number([r"Global Rank[:\s#]*([\d,]+)", r"([\d,]+)\s*\n?\s*Global Rank"], text),
        "country_rank": first_number([r"Country Rank[:\s#]*([\d,]+)", r"([\d,]+)\s*\n?\s*Country Rank"], text),
        "contests_participated": first_number([r"Contests?\s+(?:Participated|Attended)[:\s]*(\d+)",
                                               r"No\.? of (?:Rated )?Contests[:\s]*(\d+)"], text),
        "problems_solved": first_number([r"Total Problems Solved[:\s]*(\d+)", r"Problems Solved[:\s(]*(\d+)"], text),
    }
    keep = {k: v for k, v in facts.items() if v is not None}
    # One stray number is not a recognised profile: need the rating, the stars or the solved count.
    return keep if {"rating", "stars", "problems_solved"} & keep.keys() else {}


@stage("codechef")
def codechef(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    return run_profile(job, ctx, site=SITE, signal=SIGNAL, url_for=profile_url, parse=parse_profile, fields=FIELDS)
