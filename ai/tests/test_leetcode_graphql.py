"""Reading a LeetCode profile from its public GraphQL data (pure parsing and the stage's outcomes, no network)."""
import uuid

import pytest

from talnex_ai.coding.leetcode_signals import graphql, read_graphql

FOUND = {"data": {
    "matchedUser": {"username": "asha", "submitStatsGlobal": {"acSubmissionNum": [
        {"difficulty": "All", "count": 623}, {"difficulty": "Easy", "count": 164},
        {"difficulty": "Medium", "count": 359}, {"difficulty": "Hard", "count": 100}]}},
    "userContestRanking": {"attendedContestsCount": 19, "rating": 1754.1, "globalRanking": 92559},
    "userContestRankingHistory": [
        {"attended": True, "ranking": 1804, "problemsSolved": 3, "contest": {"title": "Weekly 512", "startTime": 1}},
        {"attended": True, "ranking": 0, "problemsSolved": 0, "contest": {"title": "Biweekly 188", "startTime": 2}},
        {"attended": False, "ranking": 0, "problemsSolved": 0, "contest": {"title": "Weekly 400", "startTime": 3}}]}}


def test_facts_include_solved_counts_rating_and_removed_contests():
    f = graphql.facts_from_payload(FOUND)
    assert f["solved_total"] == 623 and f["solved_hard"] == 100
    assert f["contest_rating"] == 1754 and f["contests_attended"] == 19 and f["global_ranking"] == 92559
    # only the attended contest with rank 0 and 0 solved is "removed"; the not-attended one is skipped
    assert f["removed_contests"] == [{"contest": "Biweekly 188", "start_time": 2}]


def test_a_user_with_no_contest_history_still_reads_the_solved_counts():
    payload = {"data": {"matchedUser": {"username": "x", "submitStatsGlobal": {"acSubmissionNum": [
        {"difficulty": "All", "count": 5}]}}, "userContestRanking": None, "userContestRankingHistory": None}}
    f = graphql.facts_from_payload(payload)
    assert f["solved_total"] == 5 and f["removed_contests"] == []


def test_an_unknown_user_is_none():
    assert graphql.facts_from_payload({"data": {"matchedUser": None}}) is None
    assert graphql.facts_from_payload({"errors": [{"message": "that topic does not exist."}]}) is None


def test_read_graphql_outcomes():
    assert read_graphql("u", "asha", post=lambda u, h: (200, FOUND))[0] == "ok"
    assert read_graphql("u", "ghost", post=lambda u, h: (200, {"data": {"matchedUser": None}}))[0] == "not_found"
    blocked, reason = read_graphql("u", "asha", post=lambda u, h: (403, None))
    assert blocked == "blocked" and "403" in reason
    assert read_graphql("u", "asha", post=lambda u, h: (200, "not json"))[0] == "blocked"
