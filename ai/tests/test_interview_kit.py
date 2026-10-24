"""The interview kit: which points become questions, in what order, and what is never raised."""
from talnex_ai.reports.interview_kit import MAX_QUESTIONS, build_kit


def feature(text, verdict, observed=None, testable=True):
    proof = [{"step": 1, "action": "Open", "observed": None}, {"step": 2, "action": "Final check", "observed": observed}]
    return {"claim_id": text, "text": text, "verdict": verdict, "testable": testable, "reason": "r", "proof": proof}


def paste(weight, contest="Weekly Contest 524", at="04:13"):
    return {"site": "leetcode", "signal": "leetcode_paste", "weight": weight, "contest": contest,
            "evidence": {"problem": "Last Visited Cell", "at": at, "lines": 25, "reason": "core logic pasted in one go",
                         "ranking_url": "https://leetcode.com/contest/weekly-contest-524/ranking/"}}


def report(features=(), signals=(), flags=()):
    return {"projects": [{"name": "TodoApp", "features": list(features)}], "coding_signals": list(signals), "flags": list(flags)}


def test_a_broken_feature_becomes_a_question_with_what_the_test_saw():
    (q,) = build_kit(report([feature("Real-time chat", "broken", "messages only appear after a refresh")]))
    assert q["kind"] == "feature" and '"Real-time chat"' in q["question"] and "only appear after a refresh" in q["question"]
    assert q["proof"] == {"project": "TodoApp", "claim_id": "Real-time chat"}


def test_working_features_raise_nothing():
    assert build_kit(report([feature("Add a todo", "works")])) == []


def test_order_strong_signal_then_broken_then_flag_then_partly_then_demo():
    kit = build_kit(report(
        [feature("Demo me", "could_not_test"), feature("Half done", "partly_works"), feature("Broken one", "broken")],
        [paste("strong")], [{"type": "copied_from_team", "level": "review", "reason": "Shares 72% of its code with Team 4."}]))
    assert [q["kind"] for q in kit] == ["coding", "feature", "flag", "feature", "demo"]
    assert "Weekly Contest 524" in kit[0]["question"] and kit[0]["proof"]["at"] == "04:13"


def test_one_medium_paste_is_never_raised_but_a_repeat_is():
    assert build_kit(report(signals=[paste("medium")])) == []
    (q,) = build_kit(report(signals=[paste("medium"), paste("medium", "Biweekly Contest 187")]))
    assert q["kind"] == "coding" and "not a verdict" in q["why"]


def test_info_flags_and_untestable_claims_raise_nothing_and_the_kit_is_capped():
    assert build_kit(report([feature("Needs hardware", "could_not_test", testable=False)],
                            flags=[{"type": "tutorial_copy", "level": "info", "reason": "x"}])) == []
    many = report([feature(f"Broken {i}", "broken") for i in range(9)])
    assert len(build_kit(many)) == MAX_QUESTIONS
