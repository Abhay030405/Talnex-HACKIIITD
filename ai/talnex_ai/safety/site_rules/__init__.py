"""Rules for working on someone else's live site (AGENTS.md section 8, rules 7 to 10).

- Never pay, delete or message real people, and label the free text we create "TalNex test".
- Run limits: tries per claim and live agent runs per project, counted in the database so a
  restart can't reset them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from psycopg_pool import ConnectionPool

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS

TEST_LABEL = "TalNex test"

# The label goes only where a person would type free text. A number, email or date field labelled
# "TalNex test 100" is invalid input, and the site rightly refuses it: that made a working app look broken.
LABEL_RULE = (
    f'Start free text that the site will save and show (a todo, a name, a title, a note, a comment, a message) with "{TEST_LABEL}". '
    "Never put the label into a field that needs a set format: numbers, amounts, prices, quantities, dates, times, emails, "
    "phone numbers, passwords, codes, web addresses, search boxes or drop-down choices. Type a plain valid value there "
    "(for example 100 or 2026-11-01), unless the step is testing bad input on purpose."
)

SAFETY_PREAMBLE = f"""You are testing a website that belongs to someone else, on behalf of a reviewer. Follow these rules in everything you do:
1. Never pay for anything, never enter real payment details, and never click a final "buy", "subscribe" or "donate" button.
2. Never delete accounts, data or content that you did not create in this test, and never change account settings or passwords.
3. Never send messages, emails, invitations or posts to real people. If the site would contact someone, stop.
4. {LABEL_RULE}
5. Never solve a CAPTCHA or try to get around a security check. If you hit one, stop and report "blocked".
6. Do only what the task says. Do not explore unrelated pages.
7. {DATA_NOT_ORDERS}"""


def build_task(task: str) -> str:
    """The safety rules, then the task. Every agent task goes through this."""
    return f"{SAFETY_PREAMBLE}\n\nTask:\n{task.strip()}"


class LimitReached(RuntimeError):
    """A run limit was hit. The claim stays untested with this reason; it never counts against anyone."""


@dataclass(frozen=True)
class RunLimits:
    max_tries_per_claim: int
    max_runs_per_subject: int


@dataclass(frozen=True)
class RunsUsed:
    claim_tries: int
    subject_runs: int  # live runs across every claim of the same project or candidate project


# Live runs only: sandbox requests are free and capped by tries per claim, not by agent runs.
_RUNS_USED_SQL = """
SELECT (SELECT count(*) FROM test_runs WHERE claim_id = me.id),
       (SELECT count(*)
          FROM test_runs r JOIN claims c ON c.id = r.claim_id
         WHERE r.track = 'live'
           AND ((me.project_id IS NOT NULL AND c.project_id = me.project_id)
             OR (me.candidate_project_id IS NOT NULL AND c.candidate_project_id = me.candidate_project_id)))
  FROM claims me WHERE me.id = %s::uuid
"""


def runs_used(pool: ConnectionPool, claim_id: str) -> RunsUsed:
    """Both counts in one query. An unknown claim has used nothing."""
    with pool.connection() as conn:
        row = conn.execute(_RUNS_USED_SQL, (claim_id,)).fetchone()
    return RunsUsed(int(row[0]), int(row[1])) if row else RunsUsed(0, 0)


def tries_used_for_claim(pool: ConnectionPool, claim_id: str) -> int:
    return runs_used(pool, claim_id).claim_tries


def runs_used_for_subject(pool: ConnectionPool, claim_id: str) -> int:
    return runs_used(pool, claim_id).subject_runs


def ensure_can_run(pool: ConnectionPool, claim_id: str, limits: RunLimits) -> None:
    """Raise LimitReached if one more run would go over a limit."""
    used = runs_used(pool, claim_id)
    if used.claim_tries >= limits.max_tries_per_claim:
        raise LimitReached(f"already tried this claim {used.claim_tries} times (limit {limits.max_tries_per_claim})")
    if used.subject_runs >= limits.max_runs_per_subject:
        raise LimitReached(f"already used {used.subject_runs} runs on this project (limit {limits.max_runs_per_subject})")


def next_try_number(pool: ConnectionPool, claim_id: str) -> Optional[int]:
    """The try number for the next run of a claim."""
    return tries_used_for_claim(pool, claim_id) + 1
