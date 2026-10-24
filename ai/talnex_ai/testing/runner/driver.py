"""The page driver: the only code that touches a real browser.

The executor talks to this small interface, so it can be tested without a network, and the browser
can be swapped without touching the logic.
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Protocol

from talnex_ai.testing.runner.actions import (
    Action, Click, Fill, FreshStart, Navigate, Press, Scroll, Select, Target, Upload, Wait,
)
from talnex_ai.testing.runner.devtools import DevtoolsWatch

log = logging.getLogger("talnex.runner")

ACTION_TIMEOUT_MS = 8000
NAVIGATE_TIMEOUT_MS = 30000

# Errors that mean OUR browser couldn't connect (a tunnel or proxy problem), not that the site is down.
_BROWSER_NETWORK_ERROR = re.compile(r"ERR_(?:TUNNEL|PROXY|CONNECTION|INTERNET|NETWORK|NAME_NOT_RESOLVED|TIMED_OUT)",
                                    re.IGNORECASE)


# What a plain name is looked up as, in order, for each kind of action (kind="any" targets).
ANY_ORDER = {
    "fill": [("label", None), ("placeholder", None), ("role", "textbox"), ("role", "searchbox"), ("role", "combobox")],
    "select": [("label", None), ("role", "combobox"), ("role", "listbox")],
    "upload": [("label", None), ("role", "button")],
    "click": [("role", "button"), ("role", "link"), ("role", "tab"), ("role", "checkbox"), ("role", "menuitem"),
              ("text", None)],
}


class ActionError(RuntimeError):
    """The action couldn't be done on the page (element not found, timeout...). The model is told and tries again."""


class PageDriver(Protocol):
    def url(self) -> str: ...
    def title(self) -> str: ...
    def snapshot(self) -> str: ...
    def screenshot(self) -> bytes: ...
    def perform(self, action: Action, uploads_root: Path) -> None: ...


class PlaywrightDriver:
    """Drives one page of a remote browser."""

    def __init__(self, page) -> None:
        self.page = page
        self.last_box: Optional[dict] = None  # where the last action touched the page, for the live view
        self.watch = DevtoolsWatch()
        # Handlers only read event properties: a browser call inside a handler could stall the page.
        page.on("response", lambda r: self.watch.response(id(r.request), r.request.method, r.url, r.status,
                                                           r.request.resource_type))
        page.on("requestfinished", lambda q: self.watch.finished(id(q), (q.timing or {}).get("responseEnd")))
        page.on("requestfailed", lambda q: self.watch.failed_request(q.method, q.url, q.failure or ""))
        page.on("console", lambda m: self.watch.console_message(m.type, m.text))
        page.on("pageerror", lambda e: self.watch.page_error(str(e)))

    def devtools(self) -> Optional[dict]:
        """What the developer tools saw since the last call (API calls and timings, errors, console), or None."""
        return self.watch.drain()

    def url(self) -> str:
        return self.page.url

    def title(self) -> str:
        try:
            return self.page.title()
        except Exception:
            return ""

    def snapshot(self) -> str:
        """The page as an accessibility tree: roles and names, the way a screen reader sees it. Short and
        easy for a model to read."""
        try:
            return self.page.locator("body").aria_snapshot(timeout=5000)
        except Exception as err:
            log.warning("could not read the page snapshot: %s", err)
            return ""

    def reach(self, url: str) -> bool:
        """Load the start page. False only when the BROWSER couldn't connect (a problem on our side), so the
        caller can try a fresh browser; a site that answers with an error page counts as reached."""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATE_TIMEOUT_MS)
        except Exception as err:
            return not _BROWSER_NETWORK_ERROR.search(str(err))
        return True

    def hidden_text(self) -> list[str]:
        """Comments and text a visitor can't see, for the hidden-instructions check. Never raises."""
        try:
            from talnex_ai.safety.hidden_instructions.rendered import HIDDEN_TEXT_JS

            found = self.page.evaluate(HIDDEN_TEXT_JS)
            return [str(x) for x in found] if isinstance(found, list) else []
        except Exception:
            return []

    def screenshot(self) -> bytes:
        """The whole page, not just the visible part: the result is often below the fold, and a picture
        that cuts it off makes a working feature look untestable."""
        try:
            return self.page.screenshot(type="jpeg", quality=70, full_page=True)
        except Exception:
            return self.page.screenshot(type="jpeg", quality=70)

    def _find(self, target: Target, use: str = "click"):
        if target.kind == "any":
            return self._find_any(target.name, use)
        if target.kind == "role":
            return self.page.get_by_role(target.role, name=target.name).first
        if target.kind == "label":
            return self.page.get_by_label(target.name).first
        if target.kind == "placeholder":
            return self.page.get_by_placeholder(target.name).first
        return self.page.get_by_text(target.name).first

    def _find_any(self, name: str, use: str):
        """The one element a visitor means by this name. What it is looked up by depends on what is being done to
        it; an exact match beats a partial one, and two matches are an error (the model then chooses), never a guess."""
        for attempt in range(2):
            for how, role in ANY_ORDER.get(use, ANY_ORDER["click"]):
                for exact in (True, False):
                    found = self._locator(how, role, name, exact)
                    count = found.count()
                    if count == 1:
                        return found
                    if count > 1:
                        raise ActionError(f'more than one element is called "{name}"')
            if attempt == 0:
                self.page.wait_for_timeout(600)  # the page may still be drawing; look once more
        raise ActionError(f'nothing on the page is called "{name}"')

    def _locator(self, how: str, role: Optional[str], name: str, exact: bool):
        if how == "role":
            return self.page.get_by_role(role, name=name, exact=exact)
        if how == "label":
            return self.page.get_by_label(name, exact=exact)
        if how == "placeholder":
            return self.page.get_by_placeholder(name, exact=exact)
        return self.page.get_by_text(name, exact=exact)

    def _box_of(self, target: Target, use: str = "click") -> Optional[dict]:
        """The element's position on the full page (so it lines up with the full-page screenshot). Never raises."""
        try:
            box = self._find(target, use).bounding_box(timeout=1500)
            scroll_x, scroll_y = self.page.evaluate("[window.scrollX, window.scrollY]")
            if not box:
                return None
            return {"x": round(box["x"] + scroll_x), "y": round(box["y"] + scroll_y),
                    "w": round(box["width"]), "h": round(box["height"])}
        except Exception:
            return None

    def perform(self, action: Action, uploads_root: Path) -> None:
        self.last_box = None
        if isinstance(action, (Click, Fill, Select, Upload)):
            self.last_box = self._box_of(action.target, _use(action))
        try:
            if isinstance(action, Navigate):
                url = action.url if "//" in action.url else "https://" + action.url
                self.page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATE_TIMEOUT_MS)
            elif isinstance(action, Click):
                self._find(action.target, "click").click(timeout=ACTION_TIMEOUT_MS)
            elif isinstance(action, Fill):
                self._find(action.target, "fill").fill(action.value, timeout=ACTION_TIMEOUT_MS)
            elif isinstance(action, Press):
                self.page.keyboard.press(action.key)
            elif isinstance(action, Select):
                self._find(action.target, "select").select_option(label=action.value, timeout=ACTION_TIMEOUT_MS)
            elif isinstance(action, Upload):
                path = Path(action.file)
                path = path if path.is_absolute() else uploads_root / path
                self._find(action.target, "upload").set_input_files(str(path), timeout=ACTION_TIMEOUT_MS)
            elif isinstance(action, Wait):
                self.page.wait_for_timeout(int(action.seconds * 1000))
            elif isinstance(action, Scroll):
                self.page.mouse.wheel(0, 700 if action.direction == "down" else -700)
            elif isinstance(action, FreshStart):
                self.page.context.clear_cookies()
                self.page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")
                self.page.reload(wait_until="domcontentloaded", timeout=NAVIGATE_TIMEOUT_MS)
            self._settle()
        except Exception as err:
            raise ActionError(first_line(err)) from err

    def _settle(self) -> None:
        """Give the page a moment to react before the next look."""
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        self.page.wait_for_timeout(400)


def _use(action: Action) -> str:
    return {Fill: "fill", Select: "select", Upload: "upload"}.get(type(action), "click")


def first_line(err: Exception) -> str:
    text = str(err).strip()
    return (text.splitlines()[0] if text else type(err).__name__)[:200]


@contextmanager
def connect(cdp_url: str) -> Iterator[PlaywrightDriver]:
    """Connect Playwright to a remote browser session and hand back a driver for its page."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url, timeout=60000)
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            yield PlaywrightDriver(page)
        finally:
            try:
                browser.close()
            except Exception:
                pass
