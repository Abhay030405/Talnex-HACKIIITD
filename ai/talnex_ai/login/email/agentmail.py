"""AgentMail client: reads the one sign-up inbox so a verification code or link can be used in a test.

We only ever READ here, and there's only ever ONE inbox; no other address is made. Since every site
sends to the same inbox, the email that belongs to the site being tested is picked by who sent it and
what it mentions (see `Mailbox`), never just "the newest one".

Mail from third-party sites often arrives flagged as spam or unauthenticated, so both are included.
Everything is polled from here; nothing needs a public address.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import quote

import httpx

from talnex_ai.login.email.extract import EmailHint, hint_from_parts
from talnex_ai.settings import EmailSettings

log = logging.getLogger("talnex.mail")

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
LIST_LIMIT = 5  # how many of the newest messages are looked at each time


class MailError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mail:
    message_id: str
    subject: str
    sender: str
    recipients: tuple[str, ...]
    text: str
    html: str
    timestamp: str


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class AgentMailClient:
    def __init__(self, cfg: EmailSettings, *, http: Optional[httpx.Client] = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if not cfg.api_key:
            raise MailError("AGENTMAIL_API_KEY is not set")
        if not cfg.inbox:
            raise MailError("AGENTMAIL_INBOX is not set")
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=30)
        self._sleep = sleep
        self._clock = clock

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict:
        url = f"{self.cfg.base_url}/v0/inboxes/{quote(self.cfg.inbox, safe='')}{path}"
        for attempt in range(1, 4):
            try:
                response = self.http.get(url, params=params, headers={"Authorization": f"Bearer {self.cfg.api_key}"})
            except httpx.TransportError as err:
                error = MailError(f"could not reach AgentMail: {err}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as err:
                        raise MailError("AgentMail answered with something that is not JSON") from err
                if response.status_code in (401, 403):
                    raise MailError(f"AgentMail refused the key ({response.status_code})")
                error = MailError(f"AgentMail answered {response.status_code}")
                if response.status_code not in RETRY_STATUS:
                    raise error
            if attempt == 3:
                raise error
            self._sleep(1.5 * attempt)
        raise AssertionError("unreachable")

    def recent(self, after: Optional[datetime] = None, cache: Optional[dict[str, Mail]] = None) -> list[Mail]:
        """The newest few messages that arrived after `after`, newest first. `cache` saves re-reading bodies."""
        params: dict[str, Any] = {"limit": LIST_LIMIT, "ascending": "false", "include_spam": "true",
                                  "include_unauthenticated": "true"}
        if after is not None:
            params["after"] = _iso(after)
        listing = self._get("/messages", params)
        cache = cache if cache is not None else {}
        mails = []
        for item in listing.get("messages") or listing.get("items") or []:
            message_id = item.get("message_id")
            if not message_id:
                continue
            if message_id not in cache:
                data = self._get(f"/messages/{quote(message_id, safe='')}")
                cache[message_id] = Mail(
                    message_id=message_id, subject=data.get("subject") or "", sender=data.get("from") or "",
                    recipients=tuple(data.get("to") or ()),
                    text=data.get("extracted_text") or data.get("text") or data.get("preview") or "",
                    html=data.get("html") or "", timestamp=data.get("timestamp") or "")
            mails.append(cache[message_id])
        return mails

    def newest(self, after: Optional[datetime] = None) -> Optional[Mail]:
        mails = self.recent(after)
        return mails[0] if mails else None

    def wait_for(self, after: Optional[datetime], timeout: Optional[float] = None,
                 accept: Optional[Callable[[Mail], bool]] = None) -> Optional[Mail]:
        """Poll until an accepted message arrives or time is up (None). Without `accept`, the newest counts."""
        deadline = self._clock() + (self.cfg.wait_seconds if timeout is None else timeout)
        cache: dict[str, Mail] = {}
        while True:
            for mail in self.recent(after, cache):
                if accept is None or accept(mail):
                    return mail
            if self._clock() >= deadline:
                return None
            self._sleep(self.cfg.poll_seconds)


_GENERIC_LABELS = {"www", "app", "apps", "demo", "mail", "login", "shop", "store", "api", "dev", "test", "staging",
                   "admin", "portal", "web", "site", "my", "go"}


def related_to_site(mail: Mail, site_host: str) -> bool:
    """Does this email look like it came from the site being tested? (One inbox serves every site.)"""
    host = site_host.lower().strip()
    first = host.split(".")[0]
    names = {host} | ({first} if len(first) >= 5 and first not in _GENERIC_LABELS else set())
    haystack = f"{mail.sender} {mail.subject} {mail.text} {mail.html}".lower()
    return any(name in haystack for name in names)


class Mailbox:
    """What the test loop needs: wait for this site's sign-up email and hand back only its code or link."""

    def __init__(self, client: AgentMailClient, site_host: str):
        self.client = client
        self.site_host = site_host

    def _hint(self, mail: Mail) -> EmailHint:
        return hint_from_parts(mail.subject, mail.text, mail.html, self.site_host)

    def wait_for_hint(self, since: datetime) -> Optional[EmailHint]:
        """The code or link from the newest email that mentions or comes from the site and has a code or a
        link on it. If time runs out and exactly one email arrived at all, and it has a code, that one is
        used: it can't be another site's, since nothing else arrived."""
        seen: dict[str, Mail] = {}

        def accept(mail: Mail) -> bool:
            seen[mail.message_id] = mail
            return related_to_site(mail, self.site_host) and self._hint(mail).found

        mail = self.client.wait_for(since, accept=accept)
        if mail is not None:
            return self._hint(mail)
        if len(seen) == 1:
            hint = self._hint(next(iter(seen.values())))
            if hint.found:
                return hint
        return None
