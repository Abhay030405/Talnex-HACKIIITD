"""What the test agent may do in the browser, and the safety checks that run BEFORE anything is done.

The model proposes one action at a time from this short list. Plain code decides whether it's safe,
so a clever page or a confused model can't talk its way past the rules (AGENTS.md rule 7: never pay,
delete or message people).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BeforeValidator
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from talnex_ai.testing.planner.planner import forbidden_action


class _Shape(BaseModel):
    # A model may add stray fields; ignore them rather than fail a whole step over them.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class Target(_Shape):
    """How to find an element: by what a person sees, never by code selectors."""

    # "any" is for plain code that knows only the visible name (testing/runner/simple_steps.py): the driver tries
    # label, placeholder, role and text in turn. The model is told to use the other four.
    kind: Literal["role", "label", "placeholder", "text", "any"]
    name: str = Field(min_length=1, max_length=120)
    role: Optional[str] = Field(default=None, max_length=30, description="button, link, textbox, checkbox... (kind=role)")

    @model_validator(mode="after")
    def _role_needs_a_role(self) -> "Target":
        if self.kind == "role" and not self.role:
            raise ValueError("a target of kind 'role' needs a role such as button or link")
        return self


class Navigate(_Shape):
    type: Literal["navigate"]
    url: str = Field(max_length=500)


class Click(_Shape):
    type: Literal["click"]
    target: Target


class Fill(_Shape):
    type: Literal["fill"]
    target: Target
    value: str = Field(max_length=500)


class Press(_Shape):
    type: Literal["press"]
    key: str = Field(max_length=30)


class Select(_Shape):
    type: Literal["select"]
    target: Target
    value: str = Field(max_length=200)


class Upload(_Shape):
    type: Literal["upload"]
    target: Target
    file: str = Field(max_length=300)


class Wait(_Shape):
    type: Literal["wait"]
    seconds: float = Field(gt=0, le=5)


class Scroll(_Shape):
    type: Literal["scroll"]
    direction: Literal["down", "up"]


class ReadEmail(_Shape):
    """Wait for this site's sign-up email and get its code or link. Done by the runner, not the browser:
    the model never reads the email itself, only the code or link found in it."""

    type: Literal["read_email"]


class FreshStart(_Shape):
    """Clear this browser's cookies and saved data and reload, like a brand-new visitor. Lets a test check what a
    signed-out or first-time visitor sees. Only our own test browser is touched."""
    type: Literal["fresh_start"]


class ReadSms(_Shape):
    """Wait for the text the site just sent to the team phone and get its code. Done by the runner: the
    model never reads the text itself, only the code found in it."""

    type: Literal["read_sms"]


Action = Annotated[
    Union[Navigate, Click, Fill, Press, Select, Upload, Wait, Scroll, ReadEmail, ReadSms, FreshStart], Field(discriminator="type")
]


class Decision(_Shape):
    """One turn of the agent: either the next action, or the result of the current plan step."""

    thought: Annotated[str, BeforeValidator(lambda v: v[:400] if isinstance(v, str) else v)] = ""
    action: Optional[Action] = None
    step_result: Optional[Literal["done", "failed", "blocked"]] = None
    observed: Annotated[str, BeforeValidator(lambda v: v[:400] if isinstance(v, str) else v)] = ""

    @model_validator(mode="after")
    def _exactly_one(self) -> "Decision":
        if (self.action is None) == (self.step_result is None):
            raise ValueError("give either an action or a step_result, not both and not neither")
        return self


class FinalVerdict(_Shape):
    verdict: Literal["works", "partly_works", "broken", "blocked"]
    observed: str = Field(min_length=1, max_length=500)


def describe(action: Action) -> str:
    """The action in plain words, as shown on the proof card."""
    if isinstance(action, Navigate):
        return f"Open {action.url}"
    if isinstance(action, Click):
        return f"Click {_target(action.target)}"
    if isinstance(action, Fill):
        return f'Type "{action.value}" into {_target(action.target)}'
    if isinstance(action, Press):
        return f"Press {action.key}"
    if isinstance(action, Select):
        return f'Choose "{action.value}" in {_target(action.target)}'
    if isinstance(action, Upload):
        return f"Upload {Path(action.file).name} to {_target(action.target)}"
    if isinstance(action, Wait):
        return f"Wait {action.seconds:g}s"
    if isinstance(action, ReadEmail):
        return "Read the verification email"
    if isinstance(action, ReadSms):
        return "Read the verification text message"
    if isinstance(action, FreshStart):
        return "Start fresh as a new visitor (cookies and saved data cleared)"
    return f"Scroll {action.direction}"


def _target(t: Target) -> str:
    if t.kind == "any":
        return f'"{t.name}"'
    return f'the {t.role} "{t.name}"' if t.kind == "role" else f'the {t.kind} "{t.name}"'


# ---- safety ----

_CARD_NUMBER = re.compile(r"(?:\d[ -]?){13,19}")
_CAPTCHA = re.compile(
    r"captcha|i'?m not a robot|verify (?:that )?you are (?:a )?human|are you a human|security check|press (?:and|&) hold",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    return (urlparse(url if "//" in url else "https://" + url).hostname or "").lower()


def same_site(url: str, site_host: str) -> bool:
    """Is `url` on the site being tested? Its own host, a subdomain of it, or the bare domain of a www site.

    A parent domain is NOT the same site: for myapp.vercel.app, vercel.app belongs to someone else."""
    host, site = _host(url), site_host.lower()
    return bool(host) and (host == site or host.endswith("." + site) or site == "www." + host)


def seen_address(url: str, start_url: str, seen_text: str) -> bool:
    """Was this address shown to a visitor? A real visitor opens the start address or follows what pages
    show; they don't type addresses they haven't seen. Guessed pages (/account, /profile) lead to error
    pages that spoil the pictures the checker looks at. The path is what counts, so a link written as
    '/app.html' matches the full address."""
    def path_of(address: str) -> str:
        parsed = urlparse(address if "//" in address else "https://" + address)
        return (parsed.path.rstrip("/") or "/") + (("?" + parsed.query) if parsed.query else "")

    wanted = path_of(url)
    return wanted in (path_of(start_url), "/") or wanted in seen_text or url in seen_text


# Words that can sit beside a risky word on a real control: "Proceed to checkout", "Pay ₹499 securely".
_CONTROL_FILLER = re.compile(
    r"\b(?:now|proceed|continue|go|to|the|your|my|this|order|securely|safely|here|page|today|and|with)\b|"
    r"[₹$€£]?\s?\d[\d,.]*|[^\w]+", re.IGNORECASE)


def _only_mentions(text: str, risky: str) -> bool:
    """Is the risky word just part of a longer name or title, like a demo incident called "Code Defect — Checkout
    500s"? Only for plain text being clicked: a button or link with a risky word is always refused. Text that
    starts with the risky word, or is nothing but it plus filler ("Proceed to checkout"), still counts as a control."""
    if text.strip().lower().startswith(risky.lower()):
        return False
    rest = _CONTROL_FILLER.sub(" ", text.replace(risky, " ", 1)).strip()
    return bool(rest)


def unsafe_reason(action: Action, *, site_host: str, uploads_root: Path) -> Optional[str]:
    """Why this action must not be done, or None if it's fine."""
    if isinstance(action, Navigate) and not same_site(action.url, site_host):
        return f"it would leave the site being tested ({action.url})"

    # Risky words are checked on WHAT IS BEING TOUCHED (a button called "Pay now"), not on test data
    # typed into a box: a todo called "TalNex test: buy milk" is harmless.
    if isinstance(action, (Click, Fill, Select, Upload)):
        risky = forbidden_action(action.target.name)
        if risky and isinstance(action, Click) and action.target.kind == "text" and _only_mentions(action.target.name, risky):
            risky = None
        if risky:
            return f'it involves "{risky}", which is never allowed (no paying, deleting or messaging people)'
    if isinstance(action, Fill) and _CARD_NUMBER.search(action.value):
        return "it looks like a card number, and real payment details are never entered"

    if isinstance(action, Upload):
        try:
            file = Path(action.file)
            (file if file.is_absolute() else uploads_root / file).resolve().relative_to(uploads_root.resolve())
        except (ValueError, OSError):
            return "files can only be uploaded from the test files folder"
    return None


def looks_like_captcha(snapshot: str) -> bool:
    """A human check we must not solve or get around: the step is blocked, never broken."""
    return bool(_CAPTCHA.search(snapshot))
