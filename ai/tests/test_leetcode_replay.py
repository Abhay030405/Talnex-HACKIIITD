"""The LeetCode Code Replay paste check: finding pastes in replay events and judging them by the section 18 table."""
import json

import pytest

from talnex_ai.coding.leetcode_capture import (
    HISTORY, QUESTIONS, REPLAY, ReplayBlocked, check_replays, find_pastes, judge, pick_contests,
)
from talnex_ai.settings import LeetCodeReplaySettings

CFG = LeetCodeReplaySettings()
DAY = 86400


def ev(kind, second, text=None):
    data = {"questionId": "1"}
    if text is not None:
        data["changes"] = [{"from": 0, "insert": text}]
    return {"eventType": kind, "eventData": json.dumps(data), "timestamp": f"2026-10-18T02:{second // 60:02d}:{second % 60:02d}+00:00"}


SOLUTION = "a := 0\nfor i := 1; i < len(nums); i++ {\n    if nums[i] == nums[i-1] {\n        a++\n    }\n}\nreturn a"

# van_zhang, weekly-contest-524 Q1: opened, starter code, the whole solution pasted at 02:48, run, submit
PASTED_IN_ONE_GO = [ev("0", 0), ev("2", 0), ev("7", 0, "func minDeletions(nums []int) int {\n}"), ev("10", 168, SOLUTION),
                    ev("4", 171), ev("5", 176)]


def typed(n_edits_after, paste_at=120, text=SOLUTION):
    return [ev("0", 0), ev("7", 5, "x"), ev("10", paste_at, text)] + [ev("7", paste_at + 1 + i, "y") for i in range(n_edits_after)]


def test_a_paste_is_found_with_its_time_size_and_what_came_after():
    (p,) = find_pastes(PASTED_IN_ONE_GO)
    assert (p.at_s, p.lines, p.edits_after, p.idle_before_s) == (168, 7, 0, 168)
    assert p.snippet.startswith("a := 0")


def test_typing_only_has_no_pastes():
    assert find_pastes([ev("0", 0)] + [ev("7", i, "x") for i in range(1, 50)] + [ev("5", 60)]) == []


def test_core_logic_pasted_in_one_go_is_medium():
    weight, reason = judge(find_pastes(PASTED_IN_ONE_GO)[0], CFG)
    assert weight == "medium" and "pasted in one go (7 lines)" in reason and "quiet for 168s" in reason


@pytest.mark.parametrize("events,why", [
    (typed(0, text="for x in y:\n    z()"), "short paste"),           # 2 lines: helper code
    (typed(0, paste_at=30), "personal template"),                     # pasted right after opening
    (typed(10), "worked on"),                                          # pasted, then edited a lot
])
def test_pastes_that_are_not_suspicious(events, why):
    weight, reason = judge(find_pastes(events)[0], CFG)
    assert weight == "not_suspicious" and why in reason


def contest(slug, start, rating, solved=2, attended=True):
    return {"attended": attended, "rating": rating, "problemsSolved": solved,
            "contest": {"title": slug.title(), "titleSlug": slug, "startTime": start}}


def test_contest_pick_takes_the_latest_settled_ones_and_rating_jumps():
    now = 1000 * DAY
    history = [contest("c1", 900 * DAY, 1500), contest("c2", 910 * DAY, 1650),          # c2: +150 jump
               contest("c3", 920 * DAY, 1660), contest("c4", 930 * DAY, 1670, attended=False),
               contest("c5", 940 * DAY, 1680, solved=0), contest("c6", 998 * DAY, 1690)]  # c6 is too new
    cfg = LeetCodeReplaySettings(contests=1)
    assert [c["contest"]["titleSlug"] for c in pick_contests(history, cfg, now)] == ["c3", "c2"]


class FakeEndpoint:
    """Answers the three queries like LeetCode's public data endpoint."""

    def __init__(self, replays, history=None, blocked=False):
        self.replays, self.history, self.blocked, self.calls = replays, history or [], blocked, []

    def __call__(self, url, query, variables):
        self.calls.append(variables)
        if self.blocked:
            raise ReplayBlocked("the public data endpoint answered 403")
        if query == HISTORY:
            return {"userContestRankingHistory": self.history}
        if query == QUESTIONS:
            return {"contestQuestionList": [{"title": "Q1", "titleSlug": "q1"}, {"title": "Q2", "titleSlug": "q2"}]}
        assert query == REPLAY and variables["username"] == "van_zhang"
        return {"userContestReplayEvents": self.replays.get((variables["contest"], variables["question"]))}


def test_a_contest_with_a_pasted_solution_and_one_typed_problem():
    post = FakeEndpoint({("weekly-524", "q1"): PASTED_IN_ONE_GO, ("weekly-524", "q2"): typed(10)})
    r = check_replays("https://lc/graphql", "van_zhang", CFG, post=post, contests=["weekly-524"])
    assert (r["replays_read"], len(r["pastes"]), r["suspicious"]) == (2, 2, 1)
    assert [p["weight"] for p in r["pastes"]] == ["medium", "not_suspicious"]


def test_the_same_pattern_in_several_contests_is_strong():
    slugs = ["c1", "c2", "c3"]
    post = FakeEndpoint({(s, "q1"): PASTED_IN_ONE_GO for s in slugs})
    r = check_replays("https://lc/graphql", "van_zhang", CFG, post=post, contests=slugs)
    assert [p["weight"] for p in r["pastes"]] == ["strong"] * 3 and "repeats in 3 contests" in r["pastes"][0]["reason"]


def test_one_contest_is_never_strong_and_no_replay_is_skipped():
    post = FakeEndpoint({("c1", "q1"): PASTED_IN_ONE_GO})   # q2 has no replay (None)
    r = check_replays("https://lc/graphql", "van_zhang", LeetCodeReplaySettings(repeat_contests=1), post=post, contests=["c1"])
    assert r["replays_read"] == 1 and r["pastes"][0]["weight"] == "strong"
    r = check_replays("https://lc/graphql", "van_zhang", CFG, post=post, contests=["c1"])
    assert r["pastes"][0]["weight"] == "medium"


def test_a_refused_endpoint_is_raised_for_could_not_check():  # the stage turns this into "could not check"
    with pytest.raises(ReplayBlocked):
        check_replays("https://lc/graphql", "van_zhang", CFG, post=FakeEndpoint({}, blocked=True))


def test_rating_jumps_are_measured_and_flagged_replays_kept():
    from talnex_ai.coding.leetcode_capture import rating_jumps
    history = [contest("biweekly-174", 0, 1416, solved=0), contest("weekly-524", DAY, 1836, solved=4)]   # van_zhang
    assert rating_jumps(history) == {"weekly-524": 420}
    post = FakeEndpoint({("weekly-524", "q1"): PASTED_IN_ONE_GO, ("weekly-524", "q2"): typed(10)}, history=history)
    r = check_replays("https://lc/graphql", "van_zhang", CFG, post=post, contests=["weekly-524"])
    assert r["pastes"][0]["rating_jump"] == 420
    assert list(r["flagged_replays"]) == [("weekly-524", "q1")] and r["flagged_replays"][("weekly-524", "q1")] == PASTED_IN_ONE_GO


LONG = """m, n := len(grid), len(grid[0])
v := make([]bool, m*n)
x, y := 0, 0
for {
    v[x*n+y] = true
    a, b := x, y
    switch grid[x][y] {
    case 'L':
        b--
    case 'R':
        b++
    case 'U':
        a--
    default:
        a++
    }
    if a < 0 || b < 0 || a >= m || b >= n || v[a*n+b] {
        return []int{x, y}
    }
    x, y = a, b
}"""
RENAMED = LONG.replace("grid", "g").replace("v[", "seen[").replace("v :=", "seen :=")   # same code, names changed
OTHER = "\n".join(f"total += nums[{i}] * {i}" for i in range(30))                       # a different solution


def long_paste_replay():
    accepted = {"eventType": "5", "eventData": json.dumps({"result": {"status": 10}}), "timestamp": "2026-10-18T02:05:00+00:00"}
    opened = {"eventType": "0", "eventData": json.dumps({"lang": "golang"}), "timestamp": "2026-10-18T02:00:00+00:00"}
    return [opened, ev("7", 0, "func lastVisited(grid []string) []int {\n}"), ev("10", 253, LONG), ev("4", 256), accepted]


def test_containment_and_score():
    from talnex_ai.coding.leetcode_capture.same_code import containment, score_of
    assert containment([1, 2, 3, 4], [1, 2, 3, 9]) == 75.0 and containment([], [1]) == 0.0
    assert score_of({"q1": long_paste_replay(), "q2": typed(3)}, {"q1": 4, "q2": 5}) == 4   # q2 was never accepted


def test_renamed_copies_match_and_different_code_does_not():
    from talnex_ai.coding.leetcode_capture.same_code import match_paste
    codes = {1: RENAMED, 2: RENAMED, 3: OTHER, 4: None}
    others = [{"id": i, "lang": "golang"} for i in codes] + [{"id": 5, "lang": "java"}]
    found = match_paste(LONG, "golang", others, min_pct=90, code=codes.get)
    assert (found["compared"], found["matches"], found["best_pct"]) == (3, 2, 100.0)


def test_a_long_paste_shared_with_nearby_contestants_is_strong():
    history = [contest("weekly-524", 0, 1836, solved=4)]
    history[0]["finishTimeInSeconds"] = 300
    post = FakeEndpoint({("weekly-524", "q1"): long_paste_replay()}, history=history)
    asked = []
    def near(contest_slug, qid, score, finish, me, pages):
        asked.append((contest_slug, score, finish, me))
        return [{"id": 1, "lang": "golang"}, {"id": 2, "lang": "golang"}]
    r = check_replays("https://lc/graphql", "van_zhang", CFG, post=post, contests=["weekly-524"], neighbours=near,
                      code={1: RENAMED, 2: RENAMED}.get)
    (p,) = r["pastes"]
    assert p["weight"] == "strong" and "2 people who finished near them submitted the same code" in p["reason"]
    assert asked == [("weekly-524", 0, 300, "van_zhang")]   # Q1/Q2 credits are unknown to the fake list, so score 0


def test_short_pastes_are_never_compared_and_a_failed_walk_is_could_not_check():
    from talnex_ai.browser.bql import BqlError
    post = FakeEndpoint({("weekly-524", "q1"): PASTED_IN_ONE_GO, ("weekly-524", "q2"): long_paste_replay()},
                        history=[dict(contest("weekly-524", 0, 1836), finishTimeInSeconds=300)])
    def broken(*_):
        raise BqlError("ranking page 1 answered 403")
    r = check_replays("https://lc/graphql", "van_zhang", CFG, post=post, contests=["weekly-524"], neighbours=broken)
    short, long_ = r["pastes"]
    assert "same_code" not in short and short["weight"] == "medium"
    assert long_["weight"] == "medium" and long_["same_code"]["reason"].startswith("could not check: ranking page 1 answered 403")
