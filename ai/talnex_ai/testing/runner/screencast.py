"""The live screen: a CDP screencast of the remote browser while a test runs, for the live view.

Chrome pushes frames; each is acknowledged at once (Chrome stops sending until it is) and only the newest is kept. A
small thread publishes it at most `fps` times a second, off the Playwright thread, so watching never slows the test.
Every failure here is logged and ignored: the test goes on without a live screen.
"""
from __future__ import annotations

import base64
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger("talnex.runner")


class Screencast:
    def __init__(self, page, publish: Callable[[bytes], None], *, fps: float, quality: int, width: int) -> None:
        self._publish = publish
        self._every = 1.0 / fps
        self._latest: Optional[bytes] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._cdp = page.context.new_cdp_session(page)
        self._cdp.on("Page.screencastFrame", self._on_frame)
        self._cdp.send("Page.startScreencast", {"format": "jpeg", "quality": quality, "maxWidth": width, "everyNthFrame": 2})
        self._thread = threading.Thread(target=self._loop, name="live-screen", daemon=True)
        self._thread.start()

    def _on_frame(self, params: dict) -> None:
        try:
            self._cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass
        with self._lock:
            self._latest = base64.b64decode(params.get("data") or "")

    def _loop(self) -> None:
        while not self._stop.wait(self._every):
            with self._lock:
                frame, self._latest = self._latest, None
            if frame:
                try:
                    self._publish(frame)
                except Exception as err:
                    log.debug("live screen frame not sent: %s", err)

    def stop(self) -> None:
        self._stop.set()
        try:
            self._cdp.send("Page.stopScreencast")
        except Exception:
            pass


def start(driver, publish: Callable[[bytes], None], *, fps: float, quality: int, width: int) -> Optional[Screencast]:
    """A running screencast of the driver's page, or None when it cannot start (fps 0, no page, no CDP)."""
    page = getattr(driver, "page", None)
    if page is None or fps <= 0:
        return None
    try:
        return Screencast(page, publish, fps=fps, quality=quality, width=width)
    except Exception as err:
        log.info("no live screen for this run: %s", err)
        return None
