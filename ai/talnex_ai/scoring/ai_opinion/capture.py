"""Screenshots of a live site at desktop and phone width, for the UI opinion.

One remote browser opens the site's first page, takes a desktop shot, then loads it again at phone
width and takes another. The shots go to storage so the proof card can show the picture each
opinion part is based on. A site that cannot be opened gives no shots: the UI opinion then says so
and is never scored low for it.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from talnex_ai.storage.keys import opinion_key

log = logging.getLogger("talnex.opinion_capture")

DESKTOP = {"width": 1366, "height": 800}
PHONE = {"width": 390, "height": 844}
LOAD_MS = 45_000
SETTLE_MS = 1_200


def capture(tinyfish, files, connect: Callable, project_id: str, url: str, *,
            job_id: Optional[str] = None) -> dict[str, str]:
    """{"desktop": key, "phone": key} for the shots that worked (possibly empty)."""
    keys: dict[str, str] = {}
    try:
        with tinyfish.open_session(url, job_id=job_id) as session, connect(session.cdp_url) as driver:
            page = driver.page
            for name, size in (("desktop", DESKTOP), ("phone", PHONE)):
                page.set_viewport_size(size)
                page.goto(url, wait_until="load", timeout=LOAD_MS)  # loaded at this width, as a visitor would
                page.wait_for_timeout(SETTLE_MS)
                key = opinion_key(project_id, name)
                files.put_bytes(key, page.screenshot(type="jpeg", quality=70), "image/jpeg")
                keys[name] = key
    except Exception as err:  # the site or the browser failed: fewer shots, never a mark against the team
        log.warning("could not take opinion screenshots of %s: %s", url, err)
    return keys
