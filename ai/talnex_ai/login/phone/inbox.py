"""Reads the texts forwarded by the team phone and finds the verification code in them (login ladder).

The phone app posts every incoming text to our API, which saves it in `inbound_sms` (Go owns that
table; here we only read). A text is untrusted data, like an email: the model never reads it, it only
gets the code found here. Texts are personal data and the API deletes them after 24 hours.

Only messages that reached our server after `since` count, so an old code is never reused.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from talnex_ai.login.email.extract import find_sms_code

log = logging.getLogger("talnex.sms")

LOOK_AT = 20  # how many of the newest texts are looked at each time


@dataclass(frozen=True)
class SmsCode:
    code: str


def site_hint(site_host: str) -> Optional[str]:
    """The word a text from this site would likely contain (its name), or None for a generic host."""
    parts = [p for p in (site_host or "").lower().strip().split(".") if p and p not in ("www", "app", "apps", "m")]
    name = parts[0] if parts else ""
    return name if len(name) >= 4 else None


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())  # "Acme-App" matches "acmeapp"


def _mentions(sender: str, body: str, hint: str) -> bool:
    needle = _squash(hint)
    return bool(needle) and needle in _squash(f"{sender} {body}")


def _recent(pool, since: datetime) -> list[tuple[str, str]]:
    """(sender, body) of texts that arrived after `since`, newest first."""
    with pool.connection() as conn:
        rows = conn.execute("""SELECT from_number, body FROM inbound_sms WHERE created_at > %s
                                ORDER BY created_at DESC LIMIT %s""", (since, LOOK_AT)).fetchall()
    return [(sender, body) for sender, body in rows]


def wait_for_sms_code(
    pool,
    since: datetime,
    *,
    sender_hint: Optional[str] = None,
    wait_seconds: float,
    poll_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Optional[SmsCode]:
    """Poll until a text with a code arrives for this site, or time is up (None).

    A text that mentions the site's name (`sender_hint`) is used as soon as it arrives. Any other text
    is used only if, when time runs out, exactly one distinct code arrived at all: several sites share
    the team SIM, so we never guess between codes."""
    deadline = clock() + wait_seconds
    while True:
        coded = [(sender, body, code) for sender, body in _recent(pool, since) if (code := find_sms_code(body))]
        if sender_hint:
            for sender, body, code in coded:
                if _mentions(sender, body, sender_hint):
                    return SmsCode(code)
        if clock() >= deadline:
            codes = {code for _, _, code in coded}
            return SmsCode(codes.pop()) if len(codes) == 1 else None
        sleep(poll_seconds)


class SmsBox:
    """What the test loop needs: wait for this site's text and hand back only its code."""

    def __init__(self, pool, site_host: str, *, wait_seconds: int, poll_seconds: int,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.pool, self.site_host = pool, site_host
        self.wait_seconds, self.poll_seconds = wait_seconds, poll_seconds
        self._sleep, self._clock = sleep, clock

    def wait_for_code(self, since: datetime) -> Optional[SmsCode]:
        return wait_for_sms_code(self.pool, since, sender_hint=site_hint(self.site_host),
                                 wait_seconds=self.wait_seconds, poll_seconds=self.poll_seconds,
                                 sleep=self._sleep, clock=self._clock)
