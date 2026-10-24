"""Maps a stage name to the function that runs it.

Handlers are shared by every mode: they read what they need from the database and never ask
whether the job came from a hackathon or a recruiter check.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping

from talnex_ai.db.jobs import Job


class JobTimeout(TimeoutError):
    """The job ran past its time limit."""


@dataclass
class JobContext:
    """Handed to every handler. Long handlers call check() between steps so they stop at the time limit."""

    job: Job
    pool: Any = None  # the database pool, for handlers that read or write shared tables
    started: float = field(default_factory=time.monotonic)

    @property
    def deadline(self) -> float:
        return self.started + self.job.time_limit_seconds

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def check(self) -> None:
        if self.remaining() <= 0:
            raise JobTimeout(f"{self.job.type} ran past its {self.job.time_limit_seconds}s time limit")


Handler = Callable[[Job, JobContext], Mapping[str, Any]]

_HANDLERS: Dict[str, Handler] = {}


def stage(name: str) -> Callable[[Handler], Handler]:
    """Register a handler for a stage name.

    A handler with nothing to do returns {"skipped": True, "reason": "..."}, so the stages after it still start."""

    def register(fn: Handler) -> Handler:
        if name in _HANDLERS and _HANDLERS[name] is not fn:
            raise ValueError(f"two handlers registered for stage {name!r}")
        _HANDLERS[name] = fn
        return fn

    return register


def handlers() -> Dict[str, Handler]:
    """A copy of every registered handler, by stage name."""
    return dict(_HANDLERS)
