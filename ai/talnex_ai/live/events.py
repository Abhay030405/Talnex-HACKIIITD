"""Sending live events.

Each event is one small JSON message on the Postgres channel `live` (pg_notify), so it reaches the
Go API with no new connection between Go and Python. If the `live_events` table exists (a migration
proposed in docs/live_events.md), the event is also saved there for replay; until then, saving is
skipped quietly.

Sending never raises and never blocks a check for long: an event that can't be sent is dropped with
a log line. Watching must never change what is being watched.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

log = logging.getLogger("talnex.live")

CHANNEL = "live"
VERSION = 1
MAX_PAYLOAD = 7500     # Postgres refuses NOTIFY payloads of 8000 bytes or more
MAX_TEXT = 500         # longer strings are cut, so one chatty event can't crowd out the rest
TABLE_CHECK_SECONDS = 60

OnEvent = Callable[..., None]  # on_event(kind, **data)

_table_seen: dict[int, tuple[float, bool]] = {}  # pool id -> (checked at, live_events exists)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _clip(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT - 3] + "..."
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clip(v) for v in value[:50]]
    return value


def _dump(event: dict[str, Any]) -> str:
    return json.dumps(event, default=str, separators=(",", ":"))


def encode(event: dict[str, Any]) -> str:
    """The event as JSON that always fits in one message. Long text is clipped first; if it's still too
    big, the largest data fields are dropped one by one (and named in "cut"), so the small, useful
    ones like the label still arrive."""
    event = _clip(event)
    data = dict(event.get("data") or {})
    cut: list[str] = []
    while len(_dump({**event, "data": {**data, "cut": cut} if cut else data}).encode()) > MAX_PAYLOAD and data:
        biggest = max(data, key=lambda k: len(_dump(data[k])))
        cut.append(biggest)
        del data[biggest]
    return _dump({**event, "data": {**data, "cut": cut} if cut else data})


def _has_table(pool) -> bool:
    """Whether live_events exists, re-checked every minute so the table is picked up once it's added."""
    checked = _table_seen.get(id(pool))
    if checked and time.monotonic() - checked[0] < TABLE_CHECK_SECONDS:
        return checked[1]
    with pool.connection() as conn:
        exists = conn.execute("SELECT to_regclass('public.live_events') IS NOT NULL").fetchone()[0]
    _table_seen[id(pool)] = (time.monotonic(), bool(exists))
    return bool(exists)


class Emitter:
    """Sends events about one subject (a project, a resume project, a candidate or an event).

    `child(...)` returns an emitter with more context attached (a stage, a claim, a run), so deep code
    doesn't need to know where it's called from. Calling the emitter itself is the same as `.emit`,
    so it can be passed anywhere an `on_event(kind, **data)` callback is wanted."""

    def __init__(self, pool, subject_kind: str, subject_id: str, **context: Any):
        self.pool = pool
        self.subject = {"kind": subject_kind, "id": subject_id}
        self.context = {k: v for k, v in context.items() if v is not None}

    def child(self, **context: Any) -> "Emitter":
        return Emitter(self.pool, self.subject["kind"], self.subject["id"], **{**self.context, **context})

    def emit(self, kind: str, **data: Any) -> None:
        event = {"v": VERSION, "kind": kind, "at": _now(), "subject": self.subject, **self.context, "data": data}
        try:
            payload = encode(event)
            with self.pool.connection() as conn:
                conn.execute("SELECT pg_notify(%s, %s)", (CHANNEL, payload))
                if not kind.startswith("screen.") and _has_table(self.pool):  # screen frames: live only
                    conn.execute(
                        """INSERT INTO live_events (subject_kind, subject_id, job_id, kind, payload)
                           VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb)""",
                        (self.subject["kind"], self.subject["id"], self.context.get("job_id"), kind, payload))
        except Exception as err:
            log.warning("live event %s was not sent: %s", kind, err)

    __call__ = emit


class NullEmitter:
    """An emitter that sends nothing (tests, tools, places with no subject)."""

    def child(self, **context: Any) -> "NullEmitter":
        return self

    def emit(self, kind: str, **data: Any) -> None:
        return None

    __call__ = emit


_SUBJECT_KINDS = {"project", "candidate_project", "candidate", "event"}


def for_job(pool, job, stage: Optional[str] = None):
    """The emitter for a queue job's target, with the job and stage attached."""
    if pool is None or job.target_type not in _SUBJECT_KINDS:
        return NullEmitter()
    return Emitter(pool, job.target_type, job.target_id, job_id=job.id, stage=stage or job.type,
                   pipeline=job.pipeline, run_number=job.run_number)
