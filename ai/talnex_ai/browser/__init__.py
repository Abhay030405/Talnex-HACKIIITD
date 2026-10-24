"""Browser providers for the live test runner, and a fallback between them.

The runner asks a provider for a session (`open_session`) and connects Playwright to its `cdp_url`. TinyFish is the
default provider. A self-hosted Browserless container is an optional backup: when TinyFish is unavailable (out of
budget, or its service errors), the run uses Browserless instead, so a demo keeps working without TinyFish credits.

The fallback is about provider **availability**, not about getting past a site: a self-hosted browser runs from our own
address with an ordinary fingerprint, so a site that blocks the agent blocks it the same way. A site block is still
"could not test", on either provider.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("talnex.browser")


class BrowserlessSession:
    """A session on a self-hosted Browserless container. Playwright connects to `cdp_url`; there is no per-use cost."""

    def __init__(self, cdp_url: str) -> None:
        self.cdp_url = cdp_url
        self.account = "browserless"
        self.cost_usd: float = 0.0

    def close(self) -> float:
        return 0.0

    def __enter__(self) -> "BrowserlessSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class BrowserlessProvider:
    """A Browserless (or any Chrome-over-CDP) endpoint. `ws_url` is its WebSocket address, `token` its key. On hosted
    Browserless `/stealth` the runner also solves CAPTCHAs (`PlaywrightDriver.solve_captcha`); a self-hosted container
    cannot, so a CAPTCHA there still stops the test."""

    def __init__(self, ws_url: str, token: str = "") -> None:
        self.ws_url = ws_url.rstrip("/")
        self.token = token

    def cdp_url(self) -> str:
        return f"{self.ws_url}?token={self.token}" if self.token else self.ws_url

    def open_session(self, url: Optional[str] = None, *, timeout_seconds: Optional[int] = None,
                     job_id: Optional[str] = None) -> BrowserlessSession:
        return BrowserlessSession(self.cdp_url())


class FallbackBrowser:
    """Tries the primary provider; on an availability failure (not a site block) uses the backup. If the backup also
    fails, the primary's error is raised, so the runner records an honest "could not start a browser"."""

    def __init__(self, primary, backup, *, errors: tuple = (Exception,)) -> None:
        self.primary = primary
        self.backup = backup
        self._errors = errors

    def open_session(self, url: Optional[str] = None, *, timeout_seconds: Optional[int] = None, job_id: Optional[str] = None):
        try:
            return self.primary.open_session(url, timeout_seconds=timeout_seconds, job_id=job_id)
        except self._errors as err:
            log.warning("the main browser provider was unavailable (%s); using the backup", err)
            try:
                return self.backup.open_session(url, timeout_seconds=timeout_seconds, job_id=job_id)
            except Exception as backup_err:
                log.warning("the backup browser provider also failed: %s", backup_err)
                raise err
