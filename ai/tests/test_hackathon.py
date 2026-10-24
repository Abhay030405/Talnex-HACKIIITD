import pytest

from talnex_ai.worker.hackathon_check import parse_criterion
from talnex_ai.worker.handlers.not_built_yet import skipped
from talnex_ai.worker.handlers.track_reconcile import reconcile, track_state


@pytest.mark.parametrize("outcomes, state", [
    (["passed"], "good"), (["failed", "passed"], "good"),
    (["failed", "failed"], "bad"), (["failed", "blocked", "failed"], "bad"),
    (["failed"], "unknown"), (["blocked", "blocked"], "unknown"), ([], "unknown"),
])
def test_a_track_is_good_bad_or_unknown(outcomes, state):
    assert track_state(outcomes) == state


def test_tracks_that_contradict_each_other_are_not_confirmed():
    conflict, reason = reconcile("works", "good", "bad")
    assert conflict and reason == "the live site passed but the repository tests failed, so it is not confirmed"
    assert reconcile("broken", "bad", "good")[0]
    assert reconcile("works", "good", "unknown") == (False, "")
    assert reconcile("broken", "bad", "bad") == (False, "")


def test_criteria_from_the_command_line():
    assert parse_criterion("Search:find recipes:3") == ("Search", "find recipes", 3.0)
    with pytest.raises(SystemExit):
        parse_criterion("Search:3")
    with pytest.raises(SystemExit):
        parse_criterion("Search:x:0")


def test_a_not_built_stage_says_so():
    assert skipped("the video reader is not built yet") == {"skipped": True, "reason": "the video reader is not built yet"}
