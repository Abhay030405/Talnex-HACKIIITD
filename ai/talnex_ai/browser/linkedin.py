"""LinkedIn through Browserless BrowserQL (BQL): log in to the team LinkedIn account, then open a candidate's profile so a
recruiter can see the account is real and who it belongs to.

It uses Browserless's stealth browser, residential proxy and CAPTCHA solving. Each BQL request is a fresh browser, so `login` returns the session cookies and `check_profile` sets them again. The
password goes in GraphQL variables, never in the query text, and is never logged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from talnex_ai.browser.bql import BqlError, run_bql

log = logging.getLogger("talnex.linkedin")

# LinkedIn's login page has random ids, scrambled classes, text in the proxy's language and two copies of the form (one
# hidden). So mark the visible email box, password box and the first button with text after it, then type into those.
_MARK_FORM = """(() => {
  const shown = e => e && e.offsetParent !== null;
  const email = [...document.querySelectorAll("input[type=email], #username")].find(shown);
  const pass = [...document.querySelectorAll("input[type=password]")].find(shown);
  if (!email || !pass) return "no login form";
  const after = b => pass.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING;
  const submit = [...document.querySelectorAll("button")].find(b => shown(b) && b.textContent.trim() && after(b));
  if (!submit) return "no sign-in button";
  email.dataset.talnex = "email"; pass.dataset.talnex = "password"; submit.dataset.talnex = "submit";
  return "ok";
})()"""

_LOGIN = """
mutation LinkedInLogin($email: String!, $password: String!, $mark: String!) {
  goto(url: "https://www.linkedin.com/login", waitUntil: domContentLoaded) { status }
  form: waitForSelector(selector: "input[type=password]", timeout: 20000) { time }
  mark: evaluate(content: $mark) { value }
  email: type(selector: "[data-talnex=email]", text: $email) { time }
  password: type(selector: "[data-talnex=password]", text: $password) { time }
  click(selector: "[data-talnex=submit]") { time }
  settle: waitForTimeout(time: 5000) { time }
  solve { found solved }
  afterSolve: waitForTimeout(time: 3000) { time }
  url { url }
  cookies { cookies { name value domain path secure httpOnly expires sameSite } }
}
"""

_PROFILE = """
mutation LinkedInProfile($cookies: [CookieInput]!, $url: String!) {
  cookies(cookies: $cookies) { cookies { name } }
  goto(url: $url, waitUntil: domContentLoaded) { status }
  solve { found solved }
  url { url }
  title { title }
}
"""

_SIGNED_OUT = ("/login", "/authwall", "/checkpoint", "/uas/")
_NOT_FOUND = ("/404", "/in/unavailable")


class LinkedInError(BqlError):
    """Browserless failed or answered with BQL errors: "could not check", never a verdict on the candidate."""


@dataclass
class LinkedInSession:
    ok: bool
    reason: str                       # "" when ok, else why the login did not finish (e.g. "checkpoint")
    cookies: list[dict] = field(default_factory=list)


@dataclass
class ProfileCheck:
    status: str                       # "found", "not_found", "session_expired"
    url: str                          # where LinkedIn ended up
    name: str = ""                    # from the page title, "Jane Doe - Engineer | LinkedIn" -> "Jane Doe"
    title: str = ""


class LinkedInClient:
    def __init__(self, bql_url: str, token: str, *, http: Optional[httpx.Client] = None) -> None:
        self.bql_url = bql_url.rstrip("/")
        self.token = token
        self.http = http or httpx.Client(timeout=180)

    def _run(self, query: str, variables: dict) -> dict:
        # residential proxy + human-like typing; LinkedIn blocks data-centre addresses on sight
        try:
            return run_bql(self.bql_url, self.token, query, variables, http=self.http)
        except BqlError as err:
            raise LinkedInError(str(err)) from err

    def login(self, email: str, password: str) -> LinkedInSession:
        data = self._run(_LOGIN, {"email": email, "password": password, "mark": _MARK_FORM})
        url = data["url"]["url"]
        cookies = data["cookies"]["cookies"]
        if any(c["name"] == "li_at" for c in cookies):
            return LinkedInSession(True, "", cookies)
        reason = next((p.strip("/") for p in _SIGNED_OUT if p in url), "no session cookie")
        log.warning("linkedin login did not finish: %s (captcha found=%s solved=%s)", reason,
                    data["solve"]["found"], data["solve"]["solved"])
        return LinkedInSession(False, reason)

    def check_profile(self, session: LinkedInSession, profile_url: str) -> ProfileCheck:
        data = self._run(_PROFILE, {"cookies": [_cookie_input(c) for c in session.cookies], "url": profile_url})
        return read_profile(data["url"]["url"], data["title"]["title"])


def read_profile(url: str, title: str) -> ProfileCheck:
    """Decide from where LinkedIn sent us and the page title. Kept separate so it is tested without a browser."""
    if any(p in url for p in _SIGNED_OUT):
        return ProfileCheck("session_expired", url, title=title)
    if any(p in url for p in _NOT_FOUND) or "/in/" not in url or "page not found" in title.lower():
        return ProfileCheck("not_found", url, title=title)
    name = title.split(" | ")[0].split(" - ")[0].strip()
    name = name.split(") ", 1)[-1] if name.startswith("(") else name   # "(3) Jane Doe" -> unread-count prefix
    return ProfileCheck("found", url, name=name, title=title)


def _cookie_input(cookie: dict) -> dict:
    # CookieInput takes the same fields the cookies query returns, minus nulls
    return {k: v for k, v in cookie.items() if v is not None}
