"""The place for stages that are designed but not built yet. Each one ends as "skipped" with the reason,
so the stages after it still run and the result says plainly that the check didn't happen.

None are listed right now. To add one: register it here with `skipped(...)`; to build it for real,
write its handler in its own module and delete its entry here.
"""
from __future__ import annotations

from typing import Any, Mapping


def skipped(reason: str) -> Mapping[str, Any]:
    return {"skipped": True, "reason": reason}
