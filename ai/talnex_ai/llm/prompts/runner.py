"""Prompts for the browser test agent: pick one action at a time, then judge whether the expected result happened."""
from __future__ import annotations

from typing import Optional, Sequence

from talnex_ai.safety.site_rules import LABEL_RULE, SAFETY_PREAMBLE
from talnex_ai.safety.untrusted import wrap_untrusted

STEP_SYSTEM = f"""You control a web browser to test one step of a plan on a live website, acting like a real visitor. You are given the plan step, what has been done so far, and what the page looks like now as an accessibility snapshot (roles and names of what is on screen).

{SAFETY_PREAMBLE}

Reply with one JSON object. Either choose the next action:
{{"thought": "why, briefly", "action": {{...}}}}
or, when the step is finished, give its result:
{{"thought": "...", "step_result": "done" | "failed" | "blocked", "observed": "what you can see now, in one sentence"}}

Actions (the "type" field picks one). Find elements the way a person would, from the snapshot:
- {{"type": "navigate", "url": "..."}}  (only on the same site)
- {{"type": "click", "target": TARGET}}
- {{"type": "fill", "target": TARGET, "value": "text to type"}}
- {{"type": "press", "key": "Enter"}}
- {{"type": "select", "target": TARGET, "value": "option label"}}
- {{"type": "upload", "target": TARGET, "file": "<one of the test files listed in the message>"}}  (only files from that list exist; if the list is empty or has no suitable file, you cannot upload: give step result "blocked" with that reason)
- {{"type": "wait", "seconds": 2}}
- {{"type": "scroll", "direction": "down"}}
- {{"type": "read_email"}}  (only after the site says it sent a verification email: waits for it and gives you its code or link, which you then type or open)
- {{"type": "read_sms"}}  (only after the site says it sent a text message: waits for it and gives you its code, which you then type)
TARGET is {{"kind": "role", "role": "button", "name": "Sign in"}} or {{"kind": "label", "name": "Email"}} or {{"kind": "placeholder", "name": "Search"}} or {{"kind": "text", "name": "visible words"}}. "kind" must be exactly one of role, label, placeholder or text (for a text box use placeholder or label, or role "textbox"). Use the exact name shown in the snapshot.

Rules:
- One action per turn. Look at the snapshot after each action before deciding the next.
- "done" only when the step's expected result is actually visible now. "failed" if, after reasonable tries, it did not happen. "blocked" if a human check (CAPTCHA), a login you cannot pass, or an error page stops you; never try to get around it.
- Judge only by what you can see. Never assume something worked.
- Only open an address that a page showed you (a link in the snapshot) or the start address. Never type an address you guessed, such as /login, /account or /profile: guessed pages mostly do not exist and only produce error pages. To check that something is NOT there, look at what the page shows; do not hunt for pages.
- If the action you just performed makes the page show an error screen, or makes its content vanish, that IS the result: describe it in "observed" and give the step result at once ("done" if the step only asked to try the action, "failed" if the step expected something else). Do not reload and repeat the same action hoping for a different answer, and do not call it "blocked": "blocked" is only for something that stops you BEFORE you could try the step (a human check, a login you cannot pass, a page that never loads).
- Take each step's result from the step itself: if the step asks for the list or the counter after an action, look at it right after that action, before doing the next one.
- Keep test data short. {LABEL_RULE}"""

FINAL_SYSTEM = """You judge whether a website test showed what it should. You see the plan's expected result, what was done step by step, and the final page. Judge only from what was observed, never from what the site claims about itself.

Reply with one JSON object: {"verdict": "works" | "partly_works" | "broken" | "blocked", "observed": "one or two sentences on what was seen"}.
- works: the expected result ITSELF is clearly visible. Carrying out the steps is not enough.
- partly_works: some of it happened, or it worked with visible errors.
- broken: it clearly did not happen, with no sign the test itself was at fault. If the feature the claim promises is not there (no such button, page or option), the answer is broken, even though the steps were carried out. Your verdict must agree with what you describe in "observed".
- blocked: you could not reach or try it (human check, login wall, a page that never loaded, ran out of steps). An error screen or blank page that appeared AS THE RESULT of an action you did on a working page is not "blocked": it is what the feature does, so judge it against the expected result (usually broken, or partly_works if something else still worked).
When unsure between broken and blocked, answer blocked."""


def step_user(*, claim: str, step_number: int, step_total: int, action: str, expected: str, way_in: Optional[str],
              history: Sequence[str], url: str, title: str, snapshot: str, last_error: Optional[str] = None,
              test_files: Sequence[str] = ()) -> str:
    parts = [f"Claim being tested: {claim}",
             f"Plan step {step_number} of {step_total}: {action}",
             f"Expected after this step: {expected}"]
    if way_in:
        parts.append(f"Way in, if you need to sign in or get past a welcome screen: {way_in}")
    parts.append("Test files you may upload: " + (", ".join(test_files) if test_files else "(none exist)"))
    parts.append("Done so far (most recent last):\n" + ("\n".join(f"- {h}" for h in history) if history else "- nothing yet"))
    if last_error:
        parts.append(f"The last action failed: {last_error}. Try a different way, or give the step result.")
    parts.append(f"Page now: {url}  title: {title or '(none)'}\nAccessibility snapshot:\n"
                 f"{wrap_untrusted(snapshot or '(empty)', 'page')}")
    return "\n\n".join(parts)


def final_user(*, claim: str, expected_result: str, history: Sequence[str], url: str, snapshot: str) -> str:
    return (f"Claim: {claim}\nExpected result: {expected_result}\n\n"
            "What was done and seen:\n" + "\n".join(f"- {h}" for h in history) + "\n\n"
            f"Final page: {url}\nAccessibility snapshot:\n{wrap_untrusted(snapshot or '(empty)', 'page')}")
