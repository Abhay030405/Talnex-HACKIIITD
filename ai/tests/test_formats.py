import json
import re
from typing import get_args

import pytest

from talnex_ai.formats import (
    Claim, Confidence, ClaimSource, FormatError, Result, StepKind, StepRecord, TestPlan, TestType, Verdict,
    parse_json_block, parse_list, parse_model,
)

PLAN = '{"test_type": "normal", "steps": [{"action": "open the home page", "expected": "a search box"}], ' \
       '"expected_result": "search shows results"}'


@pytest.mark.parametrize("text", [
    PLAN,
    f"```json\n{PLAN}\n```",
    f"Here is the plan:\n{PLAN}\nLet me know if you need more.",
    f"Sure! ```{PLAN}``` done",
])
def test_json_is_found_however_it_is_wrapped(text):
    assert parse_json_block(text)["test_type"] == "normal"


def test_first_complete_object_wins_when_there_are_two():
    assert parse_json_block('first {"a": 1} then {"b": 2}') == {"a": 1}


def test_braces_in_prose_before_the_json_are_skipped():
    assert parse_json_block('use {curly} style: {"a": 1}') == {"a": 1}


def test_no_json_is_a_format_error():
    with pytest.raises(FormatError, match="valid JSON"):
        parse_json_block("I could not make a plan, sorry.")


def test_parse_model_builds_a_plan():
    plan = parse_model(TestPlan, PLAN)
    assert plan.steps[0].action == "open the home page"
    assert plan.claim_id is None


def test_extra_fields_are_refused():
    with pytest.raises(FormatError, match="made_up"):
        parse_model(TestPlan, PLAN[:-1] + ', "made_up": true}')


def test_errors_say_where_the_problem_is():
    with pytest.raises(FormatError, match=r"steps"):
        parse_model(TestPlan, '{"test_type": "normal", "steps": [], "expected_result": "something"}')


def test_parse_list_bare_or_under_a_key():
    claim = json.dumps({"text": "users can sign up", "claim_group": "Accounts", "importance": 3, "source": "video"})
    assert len(parse_list(Claim, f"[{claim}]")) == 1
    assert len(parse_list(Claim, f'{{"claims": [{claim}, {claim}]}}', key="claims")) == 2
    with pytest.raises(FormatError, match="item 2"):
        parse_list(Claim, f'[{claim}, {{"text": "x"}}]')
    with pytest.raises(FormatError, match="expected a list under 'claims'"):
        parse_list(Claim, '{"other": []}', key="claims")


def test_untestable_claim_needs_a_reason():
    base = {"text": "uses machine learning", "claim_group": "AI", "importance": 2, "source": "video"}
    with pytest.raises(ValueError, match="untestable_reason"):
        Claim(**base, testable=False)
    assert Claim(**base, testable=False, untestable_reason="needs a paid account").testable is False


def test_whitespace_is_trimmed_and_limits_hold():
    claim = Claim(text="  search works  ", claim_group="Search", importance=1, source="readme")
    assert claim.text == "search works"
    with pytest.raises(ValueError):
        Claim(text="x" * 401, claim_group="Search", importance=1, source="readme")
    with pytest.raises(ValueError):
        Claim(text="search works", claim_group="Search", importance=5, source="readme")


def test_result_and_step_checks():
    with pytest.raises(ValueError, match="blank"):
        Result(claim_id="c1", verdict="works", confidence="high", reason="seen", proof_keys=["a", " "])
    with pytest.raises(ValueError):
        Result(claim_id="c1", verdict="fake", confidence="high", reason="seen")
    with pytest.raises(ValueError):
        StepRecord(step_number=0, action="click")


@pytest.mark.parametrize("table, column, shape", [
    ("results", "verdict", Verdict),
    ("results", "confidence", Confidence),
    ("claims", "source", ClaimSource),
    ("steps", "kind", StepKind),
    ("test_runs", "test_type", TestType),
])
def test_allowed_values_match_the_database(pool, table, column, shape):
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT pg_get_constraintdef(oid) FROM pg_constraint
               WHERE contype = 'c' AND conrelid = %s::regclass""", (table,)).fetchall()
    allowed = None
    for (definition,) in rows:
        if re.search(rf"\(\({column} = ANY", definition):
            allowed = set(re.findall(r"'([a-z_]+)'::text", definition))
    assert allowed == set(get_args(shape))
