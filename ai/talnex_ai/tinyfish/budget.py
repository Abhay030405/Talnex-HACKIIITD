"""The TinyFish spending guard: paid calls stop before a key's reserve is touched.

Spending is read back from usage_log, which every paid call writes, so the total is shared by
all workers and survives restarts. Each key has its own budget. The key's label is part of the
usage_log service name, e.g. `tinyfish.main.browser`. Only spending that went through TalNex is
counted; credit used elsewhere on the same account isn't visible to us.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from psycopg_pool import ConnectionPool

from talnex_ai.db.usage import log_usage
from talnex_ai.settings import TinyFishKey, TinyFishSettings


class BudgetExceeded(RuntimeError):
    """No key has enough budget left for the next paid call."""


@dataclass(frozen=True)
class KeyBudget:
    label: str
    spent: float
    limit: float

    @property
    def remaining(self) -> float:
        return max(self.limit - self.spent, 0.0)


class Budget:
    def __init__(self, cfg: TinyFishSettings, pool: ConnectionPool):
        self.cfg = cfg
        self.pool = pool

    @property
    def limit_per_key(self) -> float:
        """What may be spent per key: its budget minus the reserve."""
        return max(self.cfg.budget_usd - self.cfg.reserve_usd, 0.0)

    def spent(self, label: str) -> float:
        return self._spent_by_label().get(label, 0.0)

    def snapshot(self) -> list[KeyBudget]:
        spent = self._spent_by_label()
        return [KeyBudget(k.label, spent.get(k.label, 0.0), self.limit_per_key) for k in self.cfg.keys]

    def pick(self, needed_usd: float) -> TinyFishKey:
        """The key with the most budget left, if it can afford `needed_usd`; otherwise BudgetExceeded."""
        if not self.cfg.keys:
            raise BudgetExceeded("no TinyFish key is configured (set TINYFISH_API_KEY or TINYFISH_API_KEYS)")
        budgets = self.snapshot()
        best = max(budgets, key=lambda b: b.remaining)
        if best.remaining < needed_usd:
            left = ", ".join(f"{b.label}: ${b.remaining:.3f} left" for b in budgets)
            raise BudgetExceeded(f"TinyFish budget used up (${self.limit_per_key:.2f} per key, "
                                 f"${self.cfg.reserve_usd:.2f} kept in reserve). {left}")
        return next(k for k in self.cfg.keys if k.label == best.label)

    def record(self, label: str, kind: str, cost_usd: float, duration_ms: Optional[int] = None,
               job_id: Optional[str] = None) -> None:
        """Write one paid call to usage_log. `kind` is browser, agent or fetch."""
        log_usage(self.pool, service=f"tinyfish.{label}.{kind}", job_id=job_id,
                  duration_ms=duration_ms, cost_usd=cost_usd)

    def _spent_by_label(self) -> dict[str, float]:
        # One query for every key, instead of one query per key.
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT split_part(service, '.', 2), coalesce(sum(cost_usd), 0)
                     FROM usage_log WHERE service LIKE %s GROUP BY 1""",
                ("tinyfish.%",),
            ).fetchall()
        return {label: float(total) for label, total in rows}
