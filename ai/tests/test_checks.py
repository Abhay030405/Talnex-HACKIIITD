"""The claim split into checks, each judged on its own, and the verdict decided by plain code.

Nothing here is about one app: the cases are the general shapes of mistake (a part beyond the claim, a skipped
step, one judge blaming alone, an error page caused by the test), each tested with made-up claims."""
import json
from pathlib import Path

import pytest

from talnex_ai.formats import Check, FormatError, PlanStep, StepRecord, TestPlan
from talnex_ai.scoring.claim_points import Evidence, decide, merge_part, outcome_from_parts
from talnex_ai.testing.checks import PartMark, read_marks
from talnex_ai.testing.planner.planner import check_parts, check_plans
from talnex_ai.testing.proof_check import ProofCheck, _parse_parts
from talnex_ai.testing.retries import LadderDeps, incomplete, judge_claim
from talnex_ai.testing.runner.executor import INCOMPLETE, ExecConfig, _final_parts, execute_plan
from talnex_ai.testing.runner.runner import RunRecord
from talnex_ai.testing.scope import content_words, quote_problem, uncovered
from talnex_ai.tinyfish.client import FetchResult
from tests.fakes import FakeDriver, ScriptedModel, act, done

SITE = "https://demo.example.com/"
CLAIM = "Upload a photo and get a caption describing it"


def plan(checks=(("a caption appears under the photo", "get a caption describing it"),), test_type="normal"):
    return TestPlan(test_type=test_type, steps=[PlanStep(action="open the site", expected="the page")],
                    expected_result="a caption appears", checks=[Check(text=t, quote=q) for t, q in checks])


# ------------------------------------------------------------------ one judge's outcome from its marks


@pytest.mark.parametrize("marks, outcome", [
    (("seen", "seen"), "works"),
    (("seen", "not_seen"), "partly_works"),
    (("not_seen", "not_seen"), "broken"),
    (("not_seen", "cant_tell"), "broken"),
    (("seen", "cant_tell"), "blocked"),          # a part the test could not show: never "partly" because of us
    (("cant_tell",), "blocked"),
    (("seen", "beyond_claim"), "works"),          # a part beyond the claim is left out
    (("beyond_claim",), "blocked"),
])
def test_each_judge_gets_its_outcome_from_its_marks(marks, outcome):
    assert outcome_from_parts(marks) == outcome


# ------------------------------------------------------------------ both judges, part by part


@pytest.mark.parametrize("run, check, merged", [
    ("seen", "seen", ("seen", 2)),
    ("not_seen", "not_seen", ("not_seen", 2)),
    ("seen", "not_seen", ("disputed", 2)),
    ("not_seen", "cant_tell", ("cant_tell", 0)),      # one judge alone never blames
    ("cant_tell", "not_seen", ("cant_tell", 0)),
    ("cant_tell", "seen", ("seen", 1)),
    ("beyond_claim", "beyond_claim", ("beyond_claim", 2)),
    ("beyond_claim", "seen", ("seen", 1)),
    ("beyond_claim", "not_seen", ("beyond_claim", 1)),   # one judge can't blame, the other says it isn't the claim
    ("cant_tell", "beyond_claim", ("beyond_claim", 1)),
])
def test_a_part_is_only_not_seen_when_both_judges_say_so(run, check, merged):
    assert merge_part(run, check) == merged


def ev(run, check, ladder=False, agent="works"):
    return Evidence(agent, "works", tries=2 if ladder else 1, ladder_cleared=ladder, agent_parts=run, checker_parts=check,
                    part_names=tuple(f"part {i}" for i in range(1, len(run) + 1)))


def test_every_part_seen_by_both_works():
    d = decide(ev(("seen", "seen"), ("seen", "seen")))
    assert d.verdict == "works" and "all 2 parts were seen" in d.reason


def test_a_part_beyond_the_claim_never_lowers_a_working_feature():
    assert decide(ev(("seen", "not_seen"), ("seen", "beyond_claim"))).verdict == "works"
    assert decide(ev(("seen", "beyond_claim"), ("seen", "beyond_claim"))).verdict == "works"


def test_partly_works_needs_a_part_both_judges_saw_fail():
    d = decide(ev(("seen", "not_seen"), ("seen", "not_seen")))
    assert d.verdict == "partly_works" and "not working: part 2" in d.reason
    # one judge alone saying a part failed never marks it down: the part is unconfirmed, so "could not test"
    assert decide(ev(("seen", "not_seen"), ("seen", "cant_tell"))).verdict == "could_not_test"


def test_a_skipped_or_unclear_part_is_could_not_test_never_partly():
    d = decide(ev(("seen", "cant_tell"), ("seen", "cant_tell")))
    assert d.verdict == "could_not_test" and "could not be shown" in d.reason


def test_broken_needs_the_ladder_and_both_judges():
    assert decide(ev(("not_seen",), ("not_seen",), ladder=False, agent="broken")).verdict == "could_not_test"
    assert decide(ev(("not_seen",), ("not_seen",), ladder=True, agent="broken")).verdict == "broken"


def test_judges_contradicting_each_other_leave_it_unconfirmed():
    d = decide(ev(("seen", "seen"), ("seen", "not_seen")))
    assert (d.verdict, d.confidence) == ("could_not_test", "disagree") and "part 2" in d.reason


def test_without_parts_the_old_rules_still_apply():
    assert decide(Evidence("works", "works")).verdict == "works"


# ------------------------------------------------------------------ plans: checks tied to the claim's words


def test_meaning_words_ignore_small_words_and_endings():
    assert content_words("Add the books to a shelf") == {"add", "book", "shelf"}
    assert quote_problem(CLAIM, "get a caption describing it") is None
    assert quote_problem(CLAIM, "private pages stay blocked when signed out") == "its quote is not from the claim"
    assert quote_problem(CLAIM, "") == "it quotes no words of the claim"
    assert uncovered(CLAIM, ["Upload a photo"]) == {"get", "caption", "describ"}


def test_a_main_plan_must_split_its_claim_into_quoted_checks():
    check_parts(plan(checks=(("a photo can be chosen", "Upload a photo"),
                             ("a caption describes the photo", "get a caption describing it"))), CLAIM)
    with pytest.raises(FormatError, match="no \"checks\""):
        check_parts(plan(checks=()), CLAIM)
    with pytest.raises(FormatError, match="not from the claim"):
        check_parts(plan(checks=(("pages are private", "private pages are blocked"),)), CLAIM)
    with pytest.raises(FormatError, match="leave most of the claim untested"):
        check_parts(plan(checks=(("a photo can be chosen", "Upload a photo"),)), "Upload a photo, crop it, add a filter "
                    "and share it with a link")


def test_extra_tests_need_no_checks():
    extra = TestPlan(test_type="bad_input", steps=[PlanStep(action="submit empty", expected="a message")],
                     expected_result="a polite message")
    assert check_plans([extra], ["bad_input"], CLAIM)


# ------------------------------------------------------------------ the judges' answers


def marks_json(*statuses, observed="what was seen", seen_key="observed"):
    return json.dumps({"checks": [{"n": i, "status": s, "note": "n"} for i, s in enumerate(statuses, 1)],
                       seen_key: observed, "screenshot_clear": True})


def test_every_check_must_be_marked_exactly_once():
    assert read_marks([PartMark(n=2, status="seen"), PartMark(n=1, status="not_seen")], 2) == ("not_seen", "seen")
    with pytest.raises(FormatError, match="no mark was given for check"):
        read_marks([PartMark(n=1, status="seen")], 2)
    with pytest.raises(FormatError, match="twice"):
        read_marks([PartMark(n=1, status="seen"), PartMark(n=1, status="seen")], 1)
    with pytest.raises(FormatError, match="only 1 checks"):
        read_marks([PartMark(n=3, status="seen")], 1)


def test_a_seen_mark_at_a_starting_value_is_sent_back_by_both_judges():
    claim = "See how many tasks are left"
    zero = json.dumps({"checks": [{"n": 1, "status": "seen", "note": "the counter shows 0 of 5"}], "observed": "o",
                       "seen": "s", "screenshot_clear": True})
    with pytest.raises(FormatError, match="starting value"):
        _final_parts(zero, claim, 1)
    with pytest.raises(FormatError, match="starting value"):
        _parse_parts(zero, claim, 1)
    moved = zero.replace("shows 0 of 5", "went from 1 of 5 to 0 of 5")
    assert _final_parts(moved, claim, 1)[0] == ("seen",)


def test_the_run_judges_each_check_and_cannot_call_it_blocked():
    two = plan(checks=(("a photo can be chosen", "Upload a photo"), ("a caption appears", "get a caption describing it")))
    model = ScriptedModel(done("the try page is open"), marks_json("seen", "not_seen"))
    result = execute_plan(model, FakeDriver(), two, claim_text=CLAIM, site_url=SITE, cfg=ExecConfig(),
                          uploads_root=Path("."), save_proof=lambda n, b: f"s/{n}")
    assert (result.outcome, result.parts) == ("partly_works", ("seen", "not_seen"))
    assert "Checks:\n1. a photo can be chosen" in model.user_text(1)
    model = ScriptedModel(done("the step could not be finished"), marks_json("seen", "cant_tell"))
    result = execute_plan(model, FakeDriver(), two, claim_text=CLAIM, site_url=SITE, cfg=ExecConfig(),
                          uploads_root=Path("."), save_proof=lambda n, b: f"s/{n}")
    assert (result.outcome, result.stop_reason) == ("blocked", INCOMPLETE)


# ------------------------------------------------------------------ the ladder: an incomplete test is retried, never blamed


def rec(outcome, parts=(), stop=None):
    return RunRecord("r", 1, outcome, "seen", [StepRecord(step_number=1, action="a", proof_key="k")], stop, "main",
                     0.001, False, parts)


def climb(runs, check_parts=("seen",), check_outcome="works"):
    outcomes = iter(runs)
    deps = LadderDeps(fetch=lambda url: FetchResult(url, True), run=lambda p: next(outcomes),
                      alternate=lambda p, first: p,
                      check=lambda r, p: ProofCheck(check_outcome, "the checker's view", True, 1, check_parts),
                      sleep=lambda s: None)
    return judge_claim(plan(), SITE, deps)


def test_an_incomplete_first_try_gets_one_more_try_and_can_still_work():
    result = climb([rec("blocked", ("cant_tell",), INCOMPLETE), rec("works", ("seen",))])
    assert result.decision.verdict == "works" and len(result.runs) == 2
    assert incomplete(rec("blocked", stop="ran out of time")) and not incomplete(rec("blocked", stop="a human check appeared"))


def test_incomplete_twice_is_could_not_test_never_a_mark_against_the_site():
    result = climb([rec("blocked", ("cant_tell",), INCOMPLETE), rec("blocked", ("cant_tell",), INCOMPLETE)])
    assert result.decision.verdict == "could_not_test"


def test_incomplete_then_failing_climbs_the_whole_ladder_before_broken():
    result = climb([rec("blocked", ("cant_tell",), INCOMPLETE), rec("broken", ("not_seen",)), rec("broken", ("not_seen",))],
                   check_parts=("not_seen",), check_outcome="broken")
    assert result.decision.verdict == "broken" and len(result.runs) == 3


def test_the_ladder_decides_from_the_parts_when_both_judges_marked_them():
    result = climb([rec("partly_works", ("seen",))], check_parts=("seen",))
    assert result.decision.verdict == "works"   # the checks agree the only part is seen


# ------------------------------------------------------------------ round 3: promise vs step, fresh visitor, time, long text


def test_a_failed_promise_is_broken_even_when_the_steps_to_it_worked():
    """'Upload a photo and get a caption': uploading is the way in, the caption is the promise."""
    e = Evidence("broken", "broken", tries=2, ladder_cleared=True, agent_parts=("seen", "not_seen"),
                 checker_parts=("seen", "not_seen"), part_names=("a photo can be chosen", "a caption appears"),
                 part_promises=(False, True))
    d = decide(e)
    assert d.verdict == "broken" and "a caption appears" in d.reason
    assert outcome_from_parts(("seen", "not_seen"), (False, True)) == "broken"
    assert outcome_from_parts(("seen", "seen", "not_seen"), (True, True, False)) == "works"   # promises seen
    assert outcome_from_parts(("seen", "not_seen"), (True, True)) == "partly_works"


def test_partly_means_some_promises_work():
    e = Evidence("partly_works", "partly_works", agent_parts=("seen", "not_seen", "seen"),
                 checker_parts=("seen", "not_seen", "seen"), part_promises=(True, True, False))
    assert decide(e).verdict == "partly_works"


def test_a_plan_needs_at_least_one_promise():
    p = plan(checks=(("a photo can be chosen", "Upload a photo"), ("a caption describes it", "get a caption describing it")))
    p.checks[0].promise = False
    check_parts(p, CLAIM)
    for c in p.checks:
        c.promise = False
    with pytest.raises(FormatError, match="no check as a promise"):
        check_parts(p, CLAIM)


def test_a_fresh_visitor_action_and_long_text_never_fail_a_step():
    from talnex_ai.testing.runner.actions import Decision, FreshStart, describe

    d = Decision.model_validate({"thought": "x" * 900, "action": {"type": "fresh_start"}})
    assert isinstance(d.action, FreshStart) and len(d.thought) == 400
    assert describe(d.action).startswith("Start fresh as a new visitor")
    assert len(PartMark(n=1, status="seen", note="y" * 900).note) == 300


def test_a_longer_plan_gets_more_time():
    long_plan = TestPlan(test_type="normal", steps=[PlanStep(action=f"step {i}", expected="it is shown") for i in range(6)],
                         expected_result="done")
    ticks = iter(range(0, 10_000, 100))           # each look at the clock is 100 s later
    model = ScriptedModel(*[done("ok")] * 6, marks_json("seen"))
    result = execute_plan(model, FakeDriver(), long_plan.model_copy(update={"checks": [Check(text="done", quote="Upload a photo")]}),
                          claim_text=CLAIM, site_url=SITE, cfg=ExecConfig(max_seconds=240, seconds_per_step=60),
                          uploads_root=Path("."), save_proof=lambda n, b: f"s/{n}", clock=lambda: next(ticks))
    assert result.stop_reason == "ran out of time"   # 6 steps x 60 s = 360 s, more than 240, and the clock passed it
    assert "360s limit" in result.records[-1].observed
