"""The driver: shows a tour step on the live site, using the same runner as the tests (architecture section 32.3).

It judges nothing. A step it cannot show becomes a plain note ("I couldn't show this on the live site"), never a
mark against the project (rule 2)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Callable, Optional

from talnex_ai.formats import PlanStep, TestPlan
from talnex_ai.storage.keys import screen_key
from talnex_ai.testing.runner.executor import ExecConfig, execute_plan

log = logging.getLogger("talnex.tour")

REACH_ATTEMPTS = 3  # browsers started when the browser itself cannot connect
MAX_MISSES = 2  # after this many steps in a row that could not be shown, the rest are told, not tried


class TourBrowser(AbstractContextManager):
    """One browser session for a whole tour message. Steps run one after another in the same page."""

    def __init__(self, *, provider: Any, connect: Callable, files: Any, model: Any, site_url: str, subject_id: str,
                 uploads_root: Path, exec_config: ExecConfig, max_actions: int, on_event: Optional[Callable] = None,
                 job_id: Optional[str] = None, on_hidden_text: Optional[Callable[[list[str]], None]] = None,
                 way_in: Optional[str] = None):
        self.provider, self.connect, self.files, self.model = provider, connect, files, model
        self.site_url, self.subject_id, self.uploads_root = site_url, subject_id, uploads_root
        self.exec_config, self.actions_left, self.on_event, self.job_id = exec_config, max_actions, on_event, job_id
        self.on_hidden_text, self.way_in = on_hidden_text, way_in
        self.cost_usd = 0.0
        self.run_id = f"tour-{uuid.uuid4().hex[:12]}"
        self._misses = 0
        self._shots = 0
        self._session = None
        self._driver_cm = None
        self.driver = None

    def __enter__(self) -> "TourBrowser":
        # A remote browser sometimes cannot connect at all (a proxy or tunnel problem on its side). That says nothing
        # about the site, so a fresh browser is tried, as the tests do.
        for attempt in range(1, REACH_ATTEMPTS + 1):
            self._open()
            reach = getattr(self.driver, "reach", None)
            if reach is None or reach(self.site_url):
                return self
            log.info("the tour browser could not connect (try %d of %d); starting a fresh one", attempt, REACH_ATTEMPTS)
            self._close()
        raise RuntimeError("the browser could not reach the site")

    def _open(self) -> None:
        self._session = self.provider.open_session(self.site_url, job_id=self.job_id)
        self._session.__enter__()
        try:
            self._driver_cm = self.connect(self._session.cdp_url)
            self.driver = self._driver_cm.__enter__()
        except BaseException:
            self._close()
            raise

    def _close(self) -> None:
        for manager in (self._driver_cm, self._session):
            if manager is not None:
                try:
                    manager.__exit__(None, None, None)
                except Exception:
                    log.warning("could not close a tour browser part", exc_info=True)
        self.cost_usd += getattr(self._session, "cost_usd", 0.0) or 0.0
        self._driver_cm = self._session = self.driver = None

    def __exit__(self, *exc: Any) -> None:
        self._close()

    def _save_proof(self, number: int, picture: bytes) -> Optional[str]:
        key = screen_key(self.subject_id, self.run_id, number)
        try:
            self.files.put_bytes(key, picture, "image/jpeg")
            return key
        except Exception as err:
            log.warning("could not save tour screenshot %s: %s", key, err)
            return None

    def show(self, action: str, expect: Optional[str], *, question: str) -> Optional[str]:
        """Do one step on the live site. Returns None when it was shown, or a plain note when it could not be."""
        if self.driver is None or self._misses >= MAX_MISSES:
            return "I couldn't show this on the live site, so this step is explained from the code only."
        if self.actions_left <= 0:
            return "This tour has used its browser steps, so the rest is explained from the code only."
        plan = TestPlan(test_type="normal", steps=[PlanStep(action=action, expected=expect or "the page responds")],
                        expected_result=expect or "the page responds")
        # The tour's own action budget, plus one so a step that used its last action can still be called done.
        config = replace(self.exec_config, max_actions=self.actions_left + 1)

        def save(number: int, picture: bytes) -> Optional[str]:
            self._shots += 1
            return self._save_proof(self._shots, picture)

        try:
            result = execute_plan(self.model, self.driver, plan, claim_text=question, site_url=self.site_url, cfg=config,
                                  uploads_root=self.uploads_root, save_proof=save, way_in=self.way_in,
                                  on_hidden_text=self.on_hidden_text, job_id=self.job_id, on_event=self.on_event,
                                  judge=False)
        except Exception as err:  # our trouble, never the site's
            log.warning("tour step could not be shown: %s", err)
            self._misses += 1
            return "I couldn't show this on the live site, so this step is explained from the code only."
        self.actions_left = max(0, self.actions_left - result.actions_used)
        if result.outcome == "blocked":
            self._misses += 1
            why = result.stop_reason or "the page did not respond"
            return f"I couldn't show this on the live site ({why}), so this step is explained from the code only."
        self._misses = 0
        return None
