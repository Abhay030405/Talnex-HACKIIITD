"""Prompt for the test planner: one claim in, test plans out."""
from __future__ import annotations

from typing import Optional, Sequence

from talnex_ai.formats import Claim, TestType
from talnex_ai.safety.site_rules import LABEL_RULE
from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted
from talnex_ai.testing.planner.known_answers import KnownAnswer

TYPE_HELP: dict[str, str] = {
    "normal": "use the claimed feature the way a normal visitor would, once, and check the result",
    "known_answer": "give the feature an input whose correct answer we already know (see the known answers below) and check the answer",
    "repeat": "run the main feature twice in a row with the same input and check both runs behave the same",
    "bad_input": "give the feature ONE safe bad input (an empty field, or the wrong kind of file) and check it fails politely without crashing",
    "access": "check the way in or the page the claim describes works (signing in, guest access, or a page opening and "
              "showing what the claim says). Check that private pages are blocked only if the claim itself says so",
}

SYSTEM = f"""You write test plans for a reviewer who will check a live website like a real visitor, one step at a time.

{DATA_NOT_ORDERS}

Reply with one JSON object: {{"plans": [ ... ]}}, with exactly one plan for each test type you are asked for, no more and no fewer.
Each plan has:
- "test_type": the type name you were given.
- "steps": between 1 and 10 steps. Each step has "action" (what to do, in plain words, like telling a person) and "expected" (what should be visible afterwards, something a person could check on screen).
- "expected_result": one sentence saying what the finished test should show if the claim is true.
- "checks" (only for "normal" and "access" plans): the claim split into the 1 to 4 separate things it promises, each {{"text": "what must be visible if this part is true", "quote": "the exact words of the claim this part proves, copied from the claim", "promise": true or false}}. Every promise in the claim gets a check, and nothing that is not in the claim does. "promise" is true for what the claim says the visitor GETS (a caption appears, the count updates, the note stays after a reload) and false for a step on the way to it (open the page, choose a photo, type in the box). At least one check is a promise. A claim that something is THERE gets a check that it is there, and that check is the promise.
- When a claim is about what a signed-out or first-time visitor sees, or about signing up, signing in or creating an account, add a step "start fresh as a new visitor" before checking it: the browser may still be signed in from an earlier test.

Rules:
- The first step is always to open the site and, where needed, sign in using the way in you are given.
- Describe only what is visible on screen. Never write code, selectors or URLs of internal pages you have not been told.
- {LABEL_RULE}
- Never include steps that pay, buy, subscribe, delete accounts or data, change account settings, or send messages or emails to real people.
- "expected_result" must state the claim being TRUE as one concrete thing a person can see (for example "a share link is shown and opening it displays the same todo"). It must FAIL if the feature does not exist. Never write hedged results such as "found, or confirmed absent", "whether it exists" or "if present".
- Test ONLY what the claim says. Never add a requirement the claim does not state: no extra checks of signing out, private pages, speed, phone layout or other features. A claim that something is THERE (a page has a button, a form, a link) is proven by it being there and usable as far as the claim says; pressing that button and judging what it produces belongs to a different claim.
- Steps must USE the feature, not merely look around for it. If the feature is missing, the step that needs it will visibly not work, and that is what the test should show.
- When the claim is about something that shows the result of other actions (progress, a count, a total, an average, a percentage, a badge or a status that follows other data), the plan must first do the actions that should change it, and the last step's "expected" must name the changed value (for example "the bar shows 1 of 5 finished"). A value still at its starting point (0, 0%, empty, "none yet") after those actions does not show the feature works. For a goal or progress bar, first make progress (for example mark one book finished) and expect the bar to show it (for example "1 of 12"). If the right final value really is 0 (every item completed), write it as a change, for example "the counter goes from 1 item left to 0 items left".
- When the claim is about something done TO items that must already exist (search, filter, sort, edit, delete, rate, export, a list or a shelf), never assume the site already has them: a new visitor's list is empty. First add the items the test needs (for a search, two items with clearly different names, so narrowing the list is visible), then use the feature on them.
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
                     "the same claim. A file to upload stays one of our test files (the dog photo or the test resume): no other file exists. The previous steps were:\n" + "\n".join(f"- {s}" for s in avoid))
    if site_notes:
        parts.append("Notes about the site:\n" + wrap_untrusted(site_notes, "site_notes"))
    return "\n\n".join(parts)
