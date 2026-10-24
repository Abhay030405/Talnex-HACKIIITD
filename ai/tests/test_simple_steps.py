"""Plan steps that name one clear action are done by plain code, with no model call.

The cases are general shapes of step wording, not one app's."""
from pathlib import Path

import pytest

from talnex_ai.formats import PlanStep, TestPlan
from talnex_ai.testing.runner.actions import Click, FreshStart, Fill, Press, Select
from talnex_ai.testing.runner.driver import ActionError, PlaywrightDriver
from talnex_ai.testing.runner.executor import ExecConfig, execute_plan
from talnex_ai.testing.runner.simple_steps import parse_simple_step
from tests.fakes import FakeDriver, ScriptedModel, act, done, verdict


def only(text):
    step = parse_simple_step(text)
    assert step is not None and len(step.actions) == 1, text
    return step.actions[0]


# ------------------------------------------------------------------ reading a step


@pytest.mark.parametrize("text, name, value", [
    ("Type 'milk' into 'What needs to be done?'", "What needs to be done?", "milk"),
    ('type "TalNex test egg" in the Search box', "Search", "TalNex test egg"),
    ("Enter “5” into the Amount field.", "Amount", "5"),
    ('write "it\'s fine" into \'Title\'', "Title", "it's fine"),
])
def test_a_typing_step_becomes_a_fill(text, name, value):
    action = only(text)
    assert isinstance(action, Fill) and (action.target.name, action.value) == (name, value) and action.target.kind == "any"


@pytest.mark.parametrize("text, name", [
    ("Click Add", "Add"),
    ("click the 'Add task' button", "Add task"),
    ("Tap on the Settings link.", "Settings"),
    ("press Save", "Save"),
])
def test_a_click_step_becomes_a_click(text, name):
    action = only(text)
    assert isinstance(action, Click) and action.target.name == name


@pytest.mark.parametrize("text, key", [("press Enter", "Enter"), ("Press the Escape key", "Escape"), ("hit tab", "Tab")])
def test_a_key_step_becomes_a_key_press(text, key):
    action = only(text)
    assert isinstance(action, Press) and action.key == key


def test_other_simple_steps():
    assert isinstance(only("Choose 'Euro' from the Currency dropdown"), Select)
    assert isinstance(only("start fresh as a new visitor"), FreshStart)
    assert parse_simple_step("Open the site").actions == ()


def test_two_actions_in_one_step_are_done_in_order():
    step = parse_simple_step("Type 'milk' into 'New item' and press Enter")
    assert [type(a) for a in step.actions] == [Fill, Press]
    step = parse_simple_step("click Add, then click Done")
    assert [a.target.name for a in step.actions] == ["Add", "Done"]


def test_a_quoted_and_inside_a_value_is_not_a_second_action():
    step = parse_simple_step("Type 'salt and pepper' into 'Item'")
    assert len(step.actions) == 1 and step.actions[0].value == "salt and pepper"


@pytest.mark.parametrize("text", [
    "Sign in using the way in you are given",
    "Check that the list shows milk",
    "Upload a photo of a dog",
    "Search for TalNex test egg",                  # which box, which button? the model decides
    "Click Add to put it on the list so it shows",
    "Type 'milk' into the box and check it is there",
    "Open the site and sign in",
    "Click the first item in the list",
    "Click",
    "",
])
def test_anything_not_fully_understood_goes_to_the_model(text):
    assert parse_simple_step(text) is None


# ------------------------------------------------------------------ the step loop


def plan(*steps):
    return TestPlan(test_type="normal", steps=[PlanStep(action=a, expected="it is shown") for a in steps],
                    expected_result="the item is listed")


def run(model, driver, p, **cfg):
    return execute_plan(model, driver, p, claim_text="Add an item", site_url="https://demo.example.com/",
                        cfg=ExecConfig(**cfg), uploads_root=Path("."), save_proof=lambda n, b: f"s/{n}")


def test_simple_steps_use_no_model_calls_and_keep_a_picture_per_action():
    model = ScriptedModel(verdict("works"))      # only the final look
    driver = FakeDriver()
    result = run(model, driver, plan("Open the site", "Type 'milk' into 'New item'", "click Add"))
    assert result.outcome == "works" and len(model.calls) == 1
    assert (result.model_free_steps, result.model_calls) == (3, 0)
    assert [type(a) for a in driver.performed] == [Fill, Click]
    labels = [r.action for r in result.records]
    assert labels[:3] == ["Look: Open the site", 'Type "milk" into "New item"', 'Click "Add"']
    assert all(r.proof_key for r in result.records)


def test_a_step_that_is_not_simple_still_asks_the_model():
    model = ScriptedModel(act(type="click", target={"kind": "role", "role": "button", "name": "Go"}), done(), verdict("works"))
    result = run(model, FakeDriver(), plan("Search for eggs"))
    assert (result.model_free_steps, result.model_calls) == (0, 2)


def test_when_the_page_does_not_match_the_model_takes_over_and_is_told():
    model = ScriptedModel(done("the item is on the list"), verdict("works"))
    driver = FakeDriver(fail=frozenset({1}))
    result = run(model, driver, plan("click Add"))
    assert result.model_free_steps == 0 and result.model_calls == 1
    assert "did not work: element not found" in model.user_text(0)
    assert result.records[0].action.endswith("(did not work: element not found)")


def test_the_off_switch_sends_every_step_to_the_model():
    model = ScriptedModel(done(), verdict("works"))
    result = run(model, FakeDriver(), plan("click Add"), model_free_steps=False)
    assert (result.model_free_steps, result.model_calls) == (0, 1)


def test_an_unsafe_simple_step_is_left_to_the_model_which_refuses_it():
    model = ScriptedModel(act(type="click", target={"kind": "text", "name": "Delete account"}))
    driver = FakeDriver()
    result = run(model, driver, plan("click Delete account"))
    assert result.outcome == "blocked" and driver.performed == []


def test_simple_actions_count_toward_the_run_limit():
    model = ScriptedModel(done(), verdict("works"))
    result = run(model, FakeDriver(), plan("click Add", "click Add", "click Add"), max_actions=2)
    assert result.outcome == "blocked" and result.stop_reason == "ran out of actions"


# ------------------------------------------------------------------ finding a plain name on a real page


class Locator:
    def __init__(self, count):
        self.n = count

    def count(self):
        return self.n


class Page:
    """A pretend page: `found` maps (how, role-or-None, exact) to how many elements match a name."""

    def __init__(self, found):
        self.found, self.waited = found, 0

    def on(self, *args):
        pass

    def _loc(self, how, role, exact):
        return Locator(self.found.get((how, role, exact), 0))

    def get_by_role(self, role, name, exact):
        return self._loc("role", role, exact)

    def get_by_label(self, name, exact):
        return self._loc("label", None, exact)

    def get_by_placeholder(self, name, exact):
        return self._loc("placeholder", None, exact)

    def get_by_text(self, name, exact):
        return self._loc("text", None, exact)

    def wait_for_timeout(self, ms):
        self.waited += 1


def test_a_typing_name_is_looked_up_by_label_then_placeholder_then_textbox():
    for found in ({("label", None, True): 1}, {("placeholder", None, True): 1}, {("role", "textbox", False): 1}):
        assert PlaywrightDriver(Page(found))._find_any("Title", "fill").n == 1


def test_a_click_name_prefers_a_button_then_a_link_then_text():
    assert PlaywrightDriver(Page({("role", "link", True): 1}))._find_any("Add", "click").n == 1
    assert PlaywrightDriver(Page({("text", None, False): 1}))._find_any("Add", "click").n == 1
    with pytest.raises(ActionError, match="more than one"):
        PlaywrightDriver(Page({("role", "button", True): 2}))._find_any("Add", "click")


def test_a_name_that_is_nowhere_fails_clearly_after_one_more_look():
    page = Page({})
    with pytest.raises(ActionError, match="nothing on the page"):
        PlaywrightDriver(page)._find_any("Add", "click")
    assert page.waited == 1
