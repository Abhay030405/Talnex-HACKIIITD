"""The login ladder (architecture section 10): a legal way into the site under test, tried in order.

TalNex never breaks past a site's security. The agent takes the FIRST of these the site offers:
  1. a test login from the form (hackathon only, kept in TinyFish Vault)
  2. a guest or demo button
  3. email sign-up with our one AgentMail inbox (the agent gets the code or link with read_email)
  4. GitHub login with TalNex's own account (a saved TinyFish profile)
  5. a phone code with the team SIM (only when TEAM_PHONE_NUMBER is set; read_sms gets the code)
  6. "could not test", with the exact reason. Never counted against anyone.

This module writes the instructions for steps 2, 3, 5 and 6, and the throwaway sign-up details for
step 3. There's ONE inbox for every sign-up. The throwaway password is derived from a secret and the
SITE'S host name, so testing the same site again signs in to the account already made there.
Passwords are never stored.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Optional

from talnex_ai.settings import EmailSettings

SIGNUP_NAME = "TalNex test"


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


@dataclass(frozen=True)
class WayIn:
    instructions: str                   # given to the test agent as "the way in"
    credentials: Optional[Credentials]  # None when email sign-up isn't available
    email_enabled: bool
    phone_enabled: bool = False


def password_for(site_host: str, secret: str) -> str:
    """A throwaway password for one site: upper and lower case, digits and symbols, 16 characters, and
    the same every time for the same site (and different for every other site)."""
    digest = hmac.new(secret.encode(), site_host.lower().encode(), hashlib.sha256).hexdigest()
    return f"Tx{digest[:8]}-{digest[8:12].upper()}!7"


def credentials_for(site_host: str, cfg: EmailSettings) -> Optional[Credentials]:
    """The one inbox, plus the password for this site. None when email sign-up isn't set up."""
    if not (cfg.login_secret and cfg.inbox and cfg.api_key):
        return None
    return Credentials(cfg.inbox, password_for(site_host, cfg.login_secret))


_GUEST = '1. A guest or demo option ("Try demo", "Continue as guest", "Skip", or similar): use it, and do not create an account.'


def _dead_end(phone: bool) -> str:
    only = "Google, Apple or GitHub sign-in" if phone else "Google, Apple, GitHub or phone-number sign-in"
    return (f"If the site offers ONLY {only}, or asks for payment details or a real identity document, do not "
            'continue: give step_result "blocked" and say why in one short sentence (for example "login needs a '
            'Google account").')


def _phone_step(number: str) -> str:
    return (f"Use the team phone number ONLY when the site REQUIRES a phone number to sign up or sign in (and no "
            f"option above works). Type it exactly as {number}. When the site says it sent a text message, use the "
            "read_sms action to get the code, then type the code. Never use a temporary-number website or any other number.")


def build_way_in(site_host: str, cfg: EmailSettings, phone_number: str = "") -> WayIn:
    """The instructions the test agent follows to get into the site. An empty `phone_number` (the team
    SIM, TEAM_PHONE_NUMBER) means the phone way in is off."""
    creds = credentials_for(site_host, cfg)
    phone = (phone_number or "").strip()
    if creds is None:
        lines = ["If the site needs you to sign in or get past a welcome screen, use the first of these it offers:",
                 _GUEST, "2. Email sign-up is not available in this run."]
    else:
        lines = ["If the site needs you to sign in or get past a welcome screen, use the FIRST of these it offers:",
                 _GUEST,
                 f'2. Create an account with an email and password: email {creds.email}, password {creds.password}, '
                 f'name "{SIGNUP_NAME}". If the site asks for a verification code or link, use the read_email action '
                 "to get it, then type the code or open the link. If the site says the account already exists, sign "
                 "in with the same email and password instead."]
    rest = [_phone_step(phone), _dead_end(True)] if phone else [_dead_end(False)]
    lines += [f"{n}. {text}" for n, text in enumerate(rest, start=3)]
    lines.append("Never use real personal details." if creds is None else
                 "Never use real personal details, and never use these details for anything else.")
    return WayIn("\n".join(lines), creds, email_enabled=creds is not None, phone_enabled=bool(phone))
