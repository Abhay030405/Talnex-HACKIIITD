"""Pulls the one useful thing out of a verification email: a code, or a link on the site being tested.

An email is untrusted text, like a web page. The model never reads the email body: it only gets the
code or link found here, and a link is kept only if it points at the site being tested (the runner
also refuses to go anywhere else).
"""
from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from typing import Optional

from talnex_ai.testing.runner.actions import same_site

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BREAKS = re.compile(r"<\s*(?:br|/p|/div|/tr|/li|/h[1-6])\b[^>]*>", re.IGNORECASE)

# "Your verification code is 482913" / "OTP: 4829". Codes are one run of 4 to 8 digits.
_KEYWORD_CODE = re.compile(
    r"(?:code|otp|pin|passcode|verification|verify|confirm\w*)[^0-9]{0,40}(?<!\d)(\d{4,8})(?!\d)",
    re.IGNORECASE | re.DOTALL,
)
_LONE_SIX = re.compile(r"(?<![\d.,/:-])(\d{6})(?![\d.,/:-])")

_URL = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_VERIFY_WORDS = re.compile(r"verif|confirm|activat|token|magic|sign-?in|log-?in|auth|validate|callback", re.IGNORECASE)
_NOT_THESE = re.compile(r"unsubscribe|opt-?out|privacy|terms|preferences", re.IGNORECASE)


@dataclass(frozen=True)
class EmailHint:
    code: Optional[str]
    link: Optional[str]
    subject: str = ""

    @property
    def found(self) -> bool:
        return bool(self.code or self.link)


def html_to_text(markup: str) -> str:
    """Readable text from an HTML email."""
    text = _SCRIPT.sub(" ", markup)
    text = _BREAKS.sub("\n", text)
    text = html_lib.unescape(_TAG.sub(" ", text))
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def find_code(text: str) -> Optional[str]:
    match = _KEYWORD_CODE.search(text) or _LONE_SIX.search(text)
    return match.group(1) if match else None


def find_link(text: str, markup: str, site_host: str) -> Optional[str]:
    """The first verification-looking link that points at the site being tested."""
    for raw in _HREF.findall(markup or "") + _URL.findall(text or "") + _URL.findall(markup or ""):
        url = html_lib.unescape(raw).rstrip(".,;:!?>")
        if (url.lower().startswith("http") and _VERIFY_WORDS.search(url) and not _NOT_THESE.search(url)
                and same_site(url, site_host)):
            return url
    return None


def hint_from_parts(subject: str, text: str, markup: str, site_host: str) -> EmailHint:
    body = text or html_to_text(markup or "")
    return EmailHint(code=find_code(f"{subject}\n{body}"), link=find_link(body, markup or "", site_host),
                     subject=subject[:200])


# ---- text messages (the phone way in) ----
# A text is short and usually holds only the code, but it can also hold a phone number, a year or an
# amount. Same rule as email: one run of 4 to 8 digits, never part of a longer number.
_SMS_PREFIXED = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,4}-(\d{4,8})(?![\d-])")              # G-123456
_SMS_GROUPED = re.compile(r"(?<![\d+])(?<!\d[ -])(\d{3})-(\d{3})(?![\d]|[ -]\d)")              # 123-456
_SMS_KEYWORD = re.compile(
    r"(?:code|otp|pin|passcode|password|verification|verify|confirm\w*|security)[^0-9\n]{0,40}(?<!\d)(\d{4,8})(?!\d)",
    re.IGNORECASE,
)
_SMS_RUN = re.compile(r"(?<![\d+.,])(\d{4,8})(?![\d.,])")


def _inside_longer_number(text: str, start: int, end: int) -> bool:
    """True when the digits are part of a spaced or dashed longer number, like the phone number 800 555 1234."""
    return bool(re.search(r"\d[ \-.]$", text[max(0, start - 2):start]) or re.match(r"[ \-.]\d", text[end:end + 2]))


def _is_year(digits: str) -> bool:
    return len(digits) == 4 and digits[:2] in ("19", "20")


def find_sms_code(text: str) -> Optional[str]:
    """The verification code in a text message, or None. Never a phone number, a year or a long run of digits."""
    text = text or ""
    for match in _SMS_KEYWORD.finditer(text):
        if not _inside_longer_number(text, match.start(1), match.end(1)):
            return match.group(1)
    match = _SMS_PREFIXED.search(text)
    if match:
        return match.group(1)
    match = _SMS_GROUPED.search(text)
    if match:
        return match.group(1) + match.group(2)
    for match in _SMS_RUN.finditer(text):
        digits = match.group(1)
        if not _is_year(digits) and not _inside_longer_number(text, match.start(1), match.end(1)):
            return digits
    return None
