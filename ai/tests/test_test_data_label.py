"""The "TalNex test" label goes on free text the site saves, never into a field that needs a set format.

In a real run the agent typed "TalNex test 100" as a valid amount; the site said "not a number" and a working
converter was marked partly working."""
from talnex_ai.llm.prompts import http_test_planner, runner, test_planner
from talnex_ai.safety.site_rules import LABEL_RULE, SAFETY_PREAMBLE


def test_the_rule_names_the_fields_that_never_get_the_label():
    for word in ("numbers", "amounts", "dates", "emails", "passwords", "plain valid value"):
        assert word in LABEL_RULE


def test_every_browser_prompt_carries_the_narrow_rule_and_not_the_old_one():
    for text in (SAFETY_PREAMBLE, test_planner.SYSTEM, runner.STEP_SYSTEM):
        assert LABEL_RULE in text
        assert "Any text or data you create must start" not in text
        assert "Label every piece of test data" not in text


def test_the_backend_planner_keeps_numbers_as_numbers():
    text = http_test_planner.SYSTEM
    assert "Anything you create must start" not in text and "plain valid values of the right type" in text
