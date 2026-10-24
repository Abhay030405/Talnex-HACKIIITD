"""The test planner: a claim becomes plans, each with steps and an expected result.

Plain code decides WHICH kinds of test apply, so that part is predictable and testable. The model
only writes the steps. A guard rejects any plan that would pay, delete or message real people, or
whose expected result would pass whatever happens, whatever the model says.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

from talnex_ai.formats import Claim, FormatError, TestPlan, TestType, parse_list
from talnex_ai.llm.prompts.test_planner import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.testing.planner.known_answers import KnownAnswer, matching_entries
from talnex_ai.testing.scope import content_words, extra_requirement, quote_problem, uncovered, unchanged_value

MAX_PLANS_PER_CLAIM = 4
CHECKED_TYPES = ("normal", "access")  # the main tests: their checks decide the verdict
MAX_UNCOVERED_SHARE = 0.5             # at most half the claim's meaning words may go unquoted

# Words that suggest the feature takes something typed, picked or uploaded.
_TAKES_INPUT = re.compile(
    r"\b(upload|enter|type|search|submit|form|input|convert|paste|ask|write|fill|select|choose|query|translate|"
    r"summari[sz]e|analy[sz]e|calculate)",
    re.IGNORECASE,
)

# Things a plan must never do, even if a model suggests them (AGENTS.md rule 7).
_FORBIDDEN = re.compile(
    r"\b(pay(?:ment)?|purchase|checkout|check out|buy now|buy it now|buy button|add to cart|place (?:the |your )?order|"
    r"subscribe|subscription|donate|credit card|card number|"
    r"delete (?:the |my |your )?(?:account|profile|data|everything|all)|deactivate|close (?:the |my )?account|"
    r"change (?:the |my )?password|send (?:an? )?(?:email|e-mail|message|dm|invite|invitation)|email (?:the|a|an|my|their)|"
    r"invite (?:a |some |other )?(?:user|friend|person|people))\b",
    re.IGNORECASE,
)

# An expected result must describe the claim being TRUE, so a missing feature fails the test. A hedged
# one such as "a share option is found, or confirmed absent" passes whatever happens and proves nothing.
_HEDGED = re.compile(
    r"\bwhether\b|"
    r"\bor (?:is |are )?(?:confirm\w*|absent|missing|not (?:present|found|available|there))\b|"
    r"\bif (?:it is |it's |one is |any is |anything is )?(?:present|available|found|there|exists?)\b|"
    r"\bconfirm\w* (?:that )?(?:there is |there are )?no\b",
    re.IGNORECASE,
)


def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(0) if m else None


def hedge(text: str) -> Optional[str]:
    """The hedging wording in an expected result, or None."""
    return _first_match(_HEDGED, text)


def forbidden_action(text: str) -> Optional[str]:
    """The risky wording in a plan step, or None."""
    return _first_match(_FORBIDDEN, text)


def applicable_types(claim: Claim) -> list[TestType]:
    """The kinds of test that make sense for this claim, most important first."""
    if not claim.testable:
        return []
    if claim.claim_group.lower() == "access":
        return ["access"]
    types: list[TestType] = ["normal"]
    if matching_entries(claim):
        types.append("known_answer")
    if claim.importance == 3:
        types.append("repeat")
    if _TAKES_INPUT.search(claim.text):
        types.append("bad_input")
    return types[:MAX_PLANS_PER_CLAIM]


def check_plans(plans: list[TestPlan], wanted: Sequence[TestType], claim_text: str = "") -> list[TestPlan]:
    """Raises FormatError (so the model gets one repair try) when the plans don't fit what was asked, or test
    something the claim never promised."""
    missing = [t for t in wanted if t not in {p.test_type for p in plans}]
    if missing:
        raise FormatError(f"no plan was given for test type(s): {', '.join(missing)}")
    plans = [p for p in plans if p.test_type in wanted]  # extra, unrequested plans are dropped
    seen: set[str] = set()
    for plan in plans:
        if plan.test_type in seen:
            raise FormatError(f"more than one plan for test type {plan.test_type}; write exactly one each")
        seen.add(plan.test_type)
        for text in [plan.expected_result] + [s.action for s in plan.steps]:
            risky = forbidden_action(text)
            if risky:
                raise FormatError(f'a step mentions "{risky}", which is not allowed (never pay, delete, or message people)')
        if plan.test_type in CHECKED_TYPES and claim_text:
            check_parts(plan, claim_text)
        checked = " ".join([plan.expected_result] + [s.expected for s in plan.steps] + [c.text for c in plan.checks])
        extra = extra_requirement(claim_text, checked)
        if extra:
            raise FormatError(f"the {plan.test_type} plan checks {extra}, which the claim does not promise. Test only "
                              "what the claim says and never add requirements.")
        if plan.test_type in ("normal", "repeat"):
            start = unchanged_value(claim_text, plan.expected_result)
            if start:
                raise FormatError(f'the expected result names a starting value ("{start}"), which proves nothing. First do '
                                  "the actions that should change it, then expect the changed value (or write it as a "
                                  'change, like "from 1 item left to 0 items left").')
        for text in (plan.expected_result, plan.steps[-1].expected):
            vague = hedge(text)
            if vague:
                raise FormatError(f'the expected result says "{vague}", which would pass whatever happens. State the '
                                  "claim being TRUE as one concrete visible thing, and make the steps use the feature.")
    return plans


def check_parts(plan: TestPlan, claim_text: str) -> None:
    """A main plan splits its claim into checks, each quoting the claim, together covering most of it."""
    if not plan.checks:
        raise FormatError(f'the {plan.test_type} plan has no "checks": split the claim into the 1 to 4 things it promises')
    if len(plan.checks) > 4:
        raise FormatError(f"the {plan.test_type} plan has {len(plan.checks)} checks; use at most 4")
    for i, check in enumerate(plan.checks, start=1):
        problem = quote_problem(claim_text, check.quote)
        if problem:
            raise FormatError(f'check {i} ("{check.text}"): {problem}. Copy the exact claim words it proves into "quote".')
    left = uncovered(claim_text, [c.quote for c in plan.checks])
    if len(left) > MAX_UNCOVERED_SHARE * max(1, len(content_words(claim_text))):
        raise FormatError("the checks leave most of the claim untested (" + ", ".join(sorted(left)) + "). Every promise "
                          "in the claim needs a check.")


def plan_claim(
    client: ChatClient,
    claim: Claim,
    *,
    site_url: str,
    way_in: Optional[str] = None,
    site_notes: Optional[str] = None,
    job_id: Optional[str] = None,
    avoid: Optional[TestPlan] = None,
    only: Optional[TestType] = None,
) -> list[TestPlan]:
    """Plans for one claim. An untestable claim has none (it's shown but never scored).

    `avoid`: a plan that didn't work out; the new plan tests the same thing a different way.
    `only`: write just this one kind of test."""
    wanted = applicable_types(claim)
    if only is not None:
        wanted = [only] if wanted else []
    if not wanted:
        return []
    known: list[KnownAnswer] = matching_entries(claim) if "known_answer" in wanted else []
    previous = [f"{s.action} -> {s.expected}" for s in avoid.steps] if avoid else None

    plans = ask_json(
        client, "test_planner", SYSTEM,
        build_user(claim, wanted, site_url=site_url, way_in=way_in, site_notes=site_notes, known=known, avoid=previous),
        lambda answer: check_plans(parse_list(TestPlan, answer, key="plans"), wanted, claim.text), job_id=job_id,
    )
    order = {t: i for i, t in enumerate(wanted)}
    return sorted((p.model_copy(update={"claim_id": claim.id}) for p in plans), key=lambda p: order[p.test_type])
