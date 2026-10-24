import json
from dataclasses import dataclass

import pytest

from talnex_ai.claims.store import Subject
from talnex_ai.formats import Claim, TestPlan
from talnex_ai.llm.structured import StructuredError
from talnex_ai.testing.planner.known_answers import matching_entries
from talnex_ai.testing.planner.planner import applicable_types, forbidden_action, hedge, plan_claim
from talnex_ai.worker.handlers.test_plan import code_hint, plan_subject
from talnex_ai.worker.subjects import SubjectInfo


def claim(text, group="Core", importance=3, testable=True, cid="c1"):
    return Claim(id=cid, text=text, claim_group=group, importance=importance, source="video", testable=testable,
                 untestable_reason=None if testable else "a measurement")


def plan(test_type, expected="a list of egg recipes is shown", action="search for TalNex test egg"):
    return {"test_type": test_type, "steps": [{"action": "open the site", "expected": "the home page"},
                                             {"action": action, "expected": expected}],
            "expected_result": expected}


@dataclass
class Reply:
    text: str
    truncated: bool = False


class FakePlanner:
    def __init__(self, *answers):
        self.answers = [a if isinstance(a, str) else json.dumps(a) for a in answers]
        self.prompts = []

    def chat(self, role, messages, **options):
        self.prompts.append((role, messages[-1]["content"] if isinstance(messages[-1]["content"], str) else ""))
        return Reply(self.answers.pop(0))


@pytest.mark.parametrize("text, entry", [
    ("Upload a photo and get a caption", "image_caption"),
    ("Describe the image you upload", "image_caption"),
    ("Upload your résumé to find matching jobs", "resume_skills"),
    ("Convert between currencies with live rates", "currency_convert"),
    ("Summarise long articles", "summarize"),
    ("Translate text into 40 languages", "translate"),
    ("Built-in calculator for expenses", "arithmetic"),
])
def test_known_answers_fit_the_feature(text, entry):
    assert [e.key for e in matching_entries(claim(text))] == [entry]


@pytest.mark.parametrize("text", [
    "Add a todo item", "See the total of all expenses", "Upload a profile picture", "Convert a PDF to Word",
    "Rate a movie out of five", "Show the sum of votes",
])
def test_everyday_words_do_not_trigger_known_answer_tests(text):
    assert matching_entries(claim(text)) == []


def test_which_tests_apply():
    assert applicable_types(claim("Sign in with Google", group="Access")) == ["access"]
    assert applicable_types(claim("Search recipes by ingredient")) == ["normal", "repeat", "bad_input"]
    assert applicable_types(claim("Translate a sentence", importance=2)) == ["normal", "known_answer", "bad_input"]
    assert applicable_types(claim("Dark mode", importance=1)) == ["normal"]
    assert applicable_types(claim("95% accuracy", testable=False)) == []


@pytest.mark.parametrize("text", ["click Checkout", "enter your credit card number", "Delete the account",
                                  "send an email to the owner", "invite a friend", "subscribe to the plan"])
def test_risky_steps_are_caught(text):
    assert forbidden_action(text)


@pytest.mark.parametrize("text", ["the share button is found, or confirmed absent", "check whether a link exists",
                                  "a badge if present"])
def test_hedged_results_are_caught(text):
    assert hedge(text)


def test_safe_and_concrete_text_passes():
    assert forbidden_action("type 'TalNex test egg' into search") is None
    assert hedge("a list of egg recipes is shown") is None


def test_plans_come_back_in_order_with_the_claim_id():
    model = FakePlanner({"plans": [plan("repeat"), plan("bad_input", "a polite error is shown"), plan("normal"),
                                   plan("access")]})
    plans = plan_claim(model, claim("Search recipes by ingredient", cid="c9"), site_url="https://r.test")
    assert [p.test_type for p in plans] == ["normal", "repeat", "bad_input"]  # the unasked "access" plan is dropped
    assert all(p.claim_id == "c9" for p in plans)
    assert "Site: https://r.test" in model.prompts[0][1]


def test_a_risky_plan_gets_one_repair_then_fails():
    risky = {"plans": [plan("normal", action="click Checkout and pay")]}
    model = FakePlanner(risky, {"plans": [plan("normal")]})
    assert plan_claim(model, claim("Browse the shop", importance=1), site_url="https://s.test")[0].test_type == "normal"
    assert "not allowed" in model.prompts[1][1]
    with pytest.raises(StructuredError):
        plan_claim(FakePlanner(risky, risky), claim("Browse the shop", importance=1), site_url="https://s.test")


def test_hedged_and_missing_plans_are_sent_back():
    model = FakePlanner({"plans": [plan("normal", expected="a share link is shown, or confirmed absent")]},
                        {"plans": [plan("normal", expected="a share link is shown")]})
    plan_claim(model, claim("Share a list", importance=1), site_url="https://s.test")
    assert "would pass whatever happens" in model.prompts[1][1]
    model = FakePlanner({"plans": [plan("normal")]}, {"plans": [plan("normal"), plan("repeat")]})
    plan_claim(model, claim("Share a list"), site_url="https://s.test")
    assert "no plan was given for test type(s): repeat" in model.prompts[1][1]


def test_only_and_avoid():
    model = FakePlanner({"plans": [plan("bad_input", "a polite error is shown")]})
    previous = TestPlan.model_validate(plan("bad_input", "an error"))
    plans = plan_claim(model, claim("Search recipes"), site_url="https://r.test", only="bad_input", avoid=previous)
    assert [p.test_type for p in plans] == ["bad_input"]
    assert "DIFFERENT way" in model.prompts[0][1] and "search for TalNex test egg -> an error" in model.prompts[0][1]
    assert plan_claim(FakePlanner(), claim("x y z", testable=False), site_url="u", only="normal") == []


CHECKLIST = {"items": [{"text": "search returns results", "part": "implementation", "core": True},
                       {"text": "results match", "part": "logic"}, {"text": "empty query handled", "part": "edge"}]}


def test_planning_a_subject_records_failures_without_stopping():
    info = SubjectInfo(Subject("project", "p1"), "Team A", "https://r.test", None, None, "fresher")
    good, bad = claim("Dark mode", importance=1, cid="good"), claim("Night mode", importance=1, cid="bad")

    class OneBadClaim(FakePlanner):
        def chat(self, role, messages, **options):
            text = " ".join(str(m["content"]) for m in messages)
            if "Night mode" in text and role == "test_planner":
                return Reply("not json at all")
            if role == "claim_reader":
                return Reply(json.dumps(CHECKLIST))
            return Reply(json.dumps({"plans": [plan("normal")]}))

    result = plan_subject(OneBadClaim(), info, [good, bad], "j1")
    assert result["site_url"] == "https://r.test"
    assert result["claims"]["good"]["plans"][0]["test_type"] == "normal"
    assert result["claims"]["good"]["checklist"]["items"][0]["core"] is True
    assert result["claims"]["bad"] == {"error": "a test could not be planned (StructuredError)"}


def test_code_hint():
    note = {"how_to_try": "open /share", "needs_login": True,
            "evidence": [{"file": "app/share.py", "line": 12}, {"line": 3}]}
    assert code_hint(note) == ("How a visitor reaches it, from reading the code: open /share\n"
                               "The code puts this behind a sign-in.\nCode: app/share.py:12")
    assert code_hint({}) == ""
