"""Prompt for the test planner: one claim in, test plans out."""
from __future__ import annotations

from typing import Optional, Sequence

from talnex_ai.formats import Claim, TestType
from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted
from talnex_ai.testing.planner.known_answers import KnownAnswer

TYPE_HELP: dict[str, str] = {
    "normal": "use the claimed feature the way a normal visitor would, once, and check the result",
    "known_answer": "give the feature an input whose correct answer we already know (see the known answers below) and check the answer",
    "repeat": "run the main feature twice in a row with the same input and check both runs behave the same",
    "bad_input": "give the feature ONE safe bad input (an empty field, or the wrong kind of file) and check it fails politely without crashing",
    "access": "check signing in works, the main pages open, and private pages are blocked when signed out",
}

SYSTEM = f"""You write test plans for a reviewer who will check a live website like a real visitor, one step at a time.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"plans": [ ... ]}}, with exactly one plan for each test type you are asked for, no more and no fewer.
Each plan has:
- "test_type": the type name you were given.
- "steps": between 1 and 10 steps. Each step has "action" (what to do, in plain words, like telling a person) and "expected" (what should be visible afterwards, something a person could check on screen).
- "expected_result": one sentence saying what the finished test should show if the claim is true.

Rules:
- The first step is always to open the site and, where needed, sign in using the way in you are given.
- Describe only what is visible on screen. Never write code, selectors or URLs of internal pages you have not been told.
- Any text or data you create must start with "TalNex test".
- Never include steps that pay, buy, subscribe, delete accounts or data, change account settings, or send messages or emails to real people.
- "expected_result" must state the claim being TRUE as one concrete thing a person can see (for example "a share link is shown and opening it displays the same todo"). It must FAIL if the feature does not exist. Never write hedged results such as "found, or confirmed absent", "whether it exists" or "if present".
- Steps must USE the feature, not merely look around for it. If the feature is missing, the step that needs it will visibly not work, and that is what the test should show.
- When the claim is about something that shows the result of other actions (progress, a count, a total, an average, a percentage, a badge or a status that follows other data), the plan must first do the actions that should change it, and the last step's "expected" must name the changed value (for example "the bar shows 1 of 5 finished"). A value still at its starting point (0, 0%, empty, "none yet") after those actions does not show the feature works.
- Keep each plan short: 2 to 5 steps. Don't write a step that only looks at what the previous step already shows; put what to check in that step's "expected". The last step's "expected" is the proof of the claim."""


def build_user(
    claim: Claim,
    types: Sequence[TestType],
    *,
    site_url: str,
    way_in: Optional[str] = None,
    site_notes: Optional[str] = None,
    known: Sequence[KnownAnswer] = (),
    avoid: Optional[Sequence[str]] = None,
) -> str:
    parts = [
        f"Claim to test: {claim.text}",
        f"Feature group: {claim.claim_group}. Importance: {claim.importance} of 3.",
        f"Site: {site_url}",
        f"Way in: {way_in or 'none needed, or find the guest or demo option'}",
        "Test types to write plans for:\n" + "\n".join(f"- {t}: {TYPE_HELP.get(t, t)}" for t in types),
    ]
    if "known_answer" in types and known:
        parts.append("Known answers (use one for the known_answer plan, and put its expected answer in expected_result):\n"
                     + "\n".join(f"- {k.kind}: give it {k.use_input}; a correct answer: {k.expect}"
                                 + (f" (file: {k.asset})" if k.asset else "") for k in known))
    if avoid:
        parts.append("A previous plan for this claim did not work out. Write the same kind of test a DIFFERENT way: a "
                     "different route to the feature, different wording or a different example input, but still testing "
                     "the same claim. The previous steps were:\n" + "\n".join(f"- {s}" for s in avoid))
    if site_notes:
        parts.append("Notes about the site:\n" + wrap_untrusted(site_notes, "site_notes"))
    return "\n\n".join(parts)
