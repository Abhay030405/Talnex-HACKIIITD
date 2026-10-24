"""A test checks only what the claim promises, a count at its starting value proves nothing, and only real test
files can be uploaded. Every case here is a mistake from a real run of the planted apps."""
import json

import pytest

from talnex_ai.formats import Check, FormatError, PlanStep, TestPlan
from talnex_ai.llm.prompts.test_planner import TYPE_HELP
from talnex_ai.testing.planner.planner import check_plans
from talnex_ai.testing.proof_check import _parse as parse_check
from talnex_ai.testing.runner.executor import _final, list_test_files
from talnex_ai.testing.scope import extra_requirement, follows_actions, unchanged_value

ABOUT = "The About page explains what CaptionIt is"
GUEST = "Press Continue as guest and start using the tools without creating an account or giving an email"
GOAL = "Set a yearly reading goal with a progress bar"
LEFT = "See how many todo items are left"


def plan(expected_result, test_type="normal", step_expected="the page shows it", quote=""):
    checks = [Check(text=expected_result, quote=quote)] if quote else []
    return TestPlan(test_type=test_type, steps=[PlanStep(action="Open the site", expected=step_expected)],
                    expected_result=expected_result, checks=checks)


# ------------------------------------------------------------------ only what the claim says


@pytest.mark.parametrize("claim", [ABOUT, GUEST])
def test_a_plan_may_not_add_blocked_private_pages_to_a_claim_that_never_said_so(claim):
    invented = "The About page explains the app, while private account pages stay blocked when signed out."
    assert extra_requirement(claim, invented) == "private pages are blocked"
    with pytest.raises(FormatError, match="does not promise"):
        check_plans([plan(invented, "access", quote=claim)], ["access"], claim)


def test_a_claim_about_private_pages_may_check_them():
    claim = "Private notes are only visible to their owner and are blocked when signed out"
    assert extra_requirement(claim, "Signed out, the notes page is blocked") is None


def test_a_claim_that_you_can_sign_out_may_check_you_are_signed_out():
    # ShelfMate's account claim had its correct plan rejected twice for checking the signed-out state.
    claim = "Create an account with email and password, sign in, and sign out."
    assert extra_requirement(claim, "After signing out, the shelf is gone and the sign-in form is shown again") is None

def test_speed_and_phone_layout_are_extra_too_unless_claimed():
    assert extra_requirement("Search recipes", "results appear within 2 seconds") == "speed"
    assert extra_requirement("Search is fast", "results appear within 2 seconds") is None
    assert extra_requirement("Add a todo", "the list works on a phone screen width") == "phone or mobile layout"


def test_a_clean_plan_passes_and_the_access_type_no_longer_demands_private_pages():
    assert check_plans([plan("The About page opens and explains what CaptionIt is", "access", quote=ABOUT)], ["access"], ABOUT)
    assert "only if the claim itself says so" in TYPE_HELP["access"]


def test_the_planner_adds_the_items_a_search_or_edit_needs_first():
    # ShelfMate's search test opened an empty shelf and had nothing to search.
    from talnex_ai.llm.prompts.test_planner import SYSTEM
    assert "First add the items the test needs" in SYSTEM and "two items with clearly different names" in SYSTEM

# ------------------------------------------------------------------ a starting value is not proof


def test_a_progress_claim_at_its_starting_value_is_not_proof():
    assert follows_actions(GOAL) and follows_actions(LEFT) and not follows_actions(ABOUT)
    assert unchanged_value(GOAL, "The goal of 12 is saved: 0 of 12 books finished (0%) and an empty bar") is not None
    assert unchanged_value(GOAL, "The bar went from 0 of 12 to 1 of 12 after finishing a book") is None
    assert unchanged_value(LEFT, "The counter goes from 1 item left to 0 items left") is None
    assert unchanged_value(ABOUT, "0% of nothing") is None   # not a count claim: nothing to check


def test_the_planner_must_change_the_value_before_checking_it():
    with pytest.raises(FormatError, match="starting value"):
        check_plans([plan("The goal shows 0 of 12 books finished with a progress bar", quote=GOAL)], ["normal"], GOAL)
    assert check_plans([plan("After marking one book finished, the bar shows 1 of 12", quote=GOAL)], ["normal"], GOAL)


def test_the_runs_own_verdict_and_the_blind_check_send_back_works_at_zero():
    at_zero = json.dumps({"verdict": "works", "observed": "The goal of 12 is saved: 0 of 12 books finished (0%)."})
    with pytest.raises(FormatError, match="starting point"):
        _final(at_zero, GOAL)
    assert _final(json.dumps({"verdict": "partly_works", "observed": "0 of 12 (0%), nothing finished yet"}), GOAL).verdict == "partly_works"
    seen = json.dumps({"outcome": "works", "seen": "The progress bar shows 0 of 12 (0%).", "screenshot_clear": True})
    with pytest.raises(FormatError, match="starting point"):
        parse_check(seen, GOAL)
    moved = json.dumps({"outcome": "works", "seen": "The bar changed from 0 of 12 to 1 of 12.", "screenshot_clear": True})
    assert parse_check(moved, GOAL).outcome == "works"


# ------------------------------------------------------------------ what can be uploaded


def test_only_real_test_files_can_be_uploaded_never_a_readme(tmp_path):
    folder = tmp_path / "known_answers"
    folder.mkdir()
    for name in ("README.md", "readme.txt", "dog.jpg", "test_resume.pdf", "notes.md", "script.py"):
        (folder / name).write_bytes(b"x")
    assert list_test_files(tmp_path) == ["known_answers/dog.jpg", "known_answers/test_resume.pdf"]


# ------------------------------------------------------------------ planner wording from the demo run


def test_a_readme_claim_that_repeats_a_bullet_in_other_words_is_dropped():
    # CaptionIt's caption claim came in twice, once from the resume and once from its README.
    from talnex_ai.claims.resume_claims import repeats
    assert repeats("Upload a photo and CaptionIt writes a caption describing it.",
                   "Upload a photo and the app writes a caption describing it.")
    assert not repeats("Add a todo to the list", "Delete a todo from the list")
    assert not repeats("Search your notes as you type", "Pin a note so it moves to the top")


def test_sign_up_claims_start_fresh_and_retries_keep_to_real_test_files():
    from talnex_ai.formats import Claim
    from talnex_ai.llm.prompts.test_planner import SYSTEM, build_user
    assert "signing up, signing in or creating an account" in SYSTEM
    claim = Claim(text="Upload a photo and get a caption", claim_group="Core", importance=2, source="resume")
    retry = build_user(claim, ["normal"], site_url="https://x.test", avoid=["upload a photo of a plate of food"])
    assert "no other file exists" in retry
