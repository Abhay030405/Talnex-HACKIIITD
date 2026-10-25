"""Read a LeetCode profile from its public data endpoint (the same no-login JSON the profile page itself loads).

No account, no login: only public data. If the endpoint blocks the request (a bot challenge or a 403), the caller
reports "could not check" and the candidate is never marked down. Pure parsing lives here so it can be tested without
the network.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

# One request for the facts the stage keeps, plus the contest history (to spot removed results).
QUERY = """
query talnexProfile($username: String!) {
  matchedUser(username: $username) {
    username
    submitStatsGlobal { acSubmissionNum { difficulty count } }
  }
  userContestRanking(username: $username) {
    attendedContestsCount rating globalRanking topPercentage
  }
  userContestRankingHistory(username: $username) {
    attended rating ranking problemsSolved totalProblems
    contest { title startTime }
  }
}
""".strip()

MAX_REMOVED = 20
RECENT_RATINGS = 6


def _solved(user: Mapping[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in (user.get("submitStatsGlobal") or {}).get("acSubmissionNum") or []:
        diff, count = row.get("difficulty"), row.get("count")
        if isinstance(count, int):
            out[str(diff).lower()] = count
    return out


def _no_standing(c: Mapping[str, Any]) -> bool:
    """Attended, yet rank 0 and 0 solved: the contest's result was voided."""
    return bool(c.get("attended")) and c.get("ranking") in (0, None) and not c.get("problemsSolved")


def removed_contests(history: list) -> list[dict]:
    """Contests the user joined but has no standing in: attended, yet rank 0 and 0 solved. This is the public trace
    LeetCode leaves when it voids a contest result (for example after its own plagiarism check). Evidence, not proof."""
    out = []
    for c in history or []:
        if _no_standing(c):
            title = ((c.get("contest") or {}).get("title") or "").strip()[:120]
            out.append({"contest": title, "start_time": (c.get("contest") or {}).get("startTime")})
    return out[:MAX_REMOVED]


def facts_from_payload(payload: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Public facts from one GraphQL answer, or None when there is no such user. Raises nothing."""
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(data, Mapping):
        return None
    user = data.get("matchedUser")
    if not isinstance(user, Mapping) or not user.get("username"):
        return None

    solved = _solved(user)
    facts: dict[str, Any] = {
        "solved_total": solved.get("all"), "solved_easy": solved.get("easy"),
        "solved_medium": solved.get("medium"), "solved_hard": solved.get("hard"),
    }
    rank = data.get("userContestRanking")
    if isinstance(rank, Mapping):
        rating = rank.get("rating")
        facts["contest_rating"] = round(rating) if isinstance(rating, (int, float)) else None
        facts["contests_attended"] = rank.get("attendedContestsCount")
        facts["global_ranking"] = rank.get("globalRanking")
    history = data.get("userContestRankingHistory")
    removed = removed_contests(history if isinstance(history, list) else [])
    # A voided contest still carries the starting rating (1500), which would fake a jump in the trend: leave it out.
    rated = [c for c in (history if isinstance(history, list) else [])
             if c.get("attended") and not _no_standing(c) and isinstance(c.get("rating"), (int, float))]
    facts["recent_ratings"] = [round(c["rating"]) for c in rated[-RECENT_RATINGS:]]   # oldest first, for a trend
    last = (rated[-1].get("contest") or {}).get("startTime") if rated else None
    if isinstance(last, int):
        facts["last_contest_at"] = last
    facts["removed_contests"] = removed
    return {k: v for k, v in facts.items() if v is not None or k == "removed_contests"}
