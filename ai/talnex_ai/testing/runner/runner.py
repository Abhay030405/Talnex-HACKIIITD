"""Run one test plan for one claim on a live site, and save everything: the run, its steps, and a
screenshot of each.

  limits checked -> run row created -> TinyFish browser opened -> plan executed -> steps and
  screenshots saved -> browser ended (always) -> run row closed

A problem on our side never marks a claim broken: the run ends as "error" or "blocked" and the claim
stays untested for that try.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ContextManager, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.formats import Claim, StepRecord, TestPlan
from talnex_ai.llm.structured import ChatClient, StructuredError
from talnex_ai.safety.site_rules import RunLimits, ensure_can_run, next_try_number
from talnex_ai.settings import RunnerSettings
from talnex_ai.storage import Store
from talnex_ai.storage.keys import screen_key
from talnex_ai.testing.runner import driver as driver_module
from talnex_ai.testing.runner import store
from talnex_ai.testing.runner.executor import ExecConfig, ExecResult, MailboxLike, Outcome, SmsBoxLike, execute_plan
from talnex_ai.tinyfish.budget import BudgetExceeded
from talnex_ai.tinyfish.client import TinyFishClient, TinyFishError

log = logging.getLogger("talnex.runner")

# The runner's own conclusion -> what the database stores for the run.
DB_OUTCOME = {"works": "passed", "partly_works": "passed", "broken": "failed", "blocked": "blocked"}
REACH_ATTEMPTS = 3  # browsers started for one run when the browser itself can't connect

Connector = Callable[[str], ContextManager]


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    try_number: int
    outcome: Outcome                # works / partly_works / broken / blocked, as the test run concluded
    observed: str
    steps: list[StepRecord]
    stop_reason: Optional[str]
    session_account: Optional[str]  # which TinyFish key paid for it
    cost_usd: Optional[float]
    vision_used: bool


def run_plan(
    *,
    pool: ConnectionPool,
    store_files: Store,
    tinyfish: TinyFishClient,
    client: ChatClient,
    claim: Claim,
    plan: TestPlan,
    site_url: str,
    subject_id: str,
    limits: RunLimits,
    runner_cfg: RunnerSettings,
    uploads_root: Path,
    way_in: Optional[str] = None,
    mailbox: Optional[MailboxLike] = None,
    smsbox: Optional[SmsBoxLike] = None,
    on_hidden_text: Optional[Callable[[list[str]], None]] = None,
    job_id: Optional[str] = None,
    connect: Connector = driver_module.connect,
) -> RunRecord:
    """Run one plan. Raises LimitReached when a run limit is hit (nothing is created then)."""
    if claim.id is None:
        raise ValueError("the claim must be saved before it can be tested")
    ensure_can_run(pool, claim.id, limits)
    try_number = next_try_number(pool, claim.id) or 1
    run_id = store.create_run(pool, claim.id, try_number, plan.test_type, method="browser")

    result: Optional[ExecResult] = None
    account: Optional[str] = None
    cost = 0.0
    db_outcome = "error"
    problem: Optional[str] = None

    def save_proof(number: int, picture: bytes) -> Optional[str]:
        key = screen_key(subject_id, run_id, number)
        try:
            store_files.put_bytes(key, picture, "image/jpeg")
            return key
        except Exception as err:  # the step is still recorded, just without its picture
            log.warning("could not save screenshot %s: %s", key, err)
            return None

    config = ExecConfig(runner_cfg.max_actions, runner_cfg.max_actions_per_step, runner_cfg.max_seconds,
                        runner_cfg.snapshot_chars)
    try:
        # A remote browser sometimes can't connect at all (a tunnel error on our side). That says nothing
        # about the site, so the start page is loaded first and, if the browser couldn't connect, a fresh
        # browser is tried.
        for attempt in range(1, REACH_ATTEMPTS + 1):
            reached = True
            with tinyfish.open_session(site_url, job_id=job_id) as session:
                account = session.account
                with connect(session.cdp_url) as driver:
                    reach = getattr(driver, "reach", None)
                    if reach is not None and attempt < REACH_ATTEMPTS and not reach(site_url):
                        log.info("the browser could not connect (try %d of %d); starting a fresh one",
                                 attempt, REACH_ATTEMPTS)
                        reached = False
                    else:
                        result = execute_plan(
                            client, driver, plan, claim_text=claim.text, site_url=site_url, cfg=config,
                            uploads_root=uploads_root, save_proof=save_proof, way_in=way_in, mailbox=mailbox,
                            smsbox=smsbox, on_hidden_text=on_hidden_text, job_id=job_id)
            # The session's cost is only known once it has closed, so it's counted here, for every attempt.
            cost += session.cost_usd or 0.0
            if reached:
                break
        db_outcome = DB_OUTCOME[result.outcome] if result else "error"
    except (BudgetExceeded, TinyFishError) as err:
        problem = f"could not start a browser: {err}"
        db_outcome = "blocked"
    except StructuredError as err:
        problem = f"the test agent could not decide what to do: {err}"
    except Exception as err:  # anything else is our problem, never the site's
        log.exception("test run %s crashed", run_id)
        problem = f"the test run hit a problem on our side: {type(err).__name__}"
    finally:
        try:
            store.add_steps(pool, run_id, result.records if result else [])
            store.finish_run(pool, run_id, db_outcome)
        except Exception:
            log.exception("could not save run %s", run_id)

    if result is None:
        return RunRecord(run_id, try_number, "blocked", problem or "the test could not run", [], problem, account,
                         cost or None, False)
    return RunRecord(run_id, try_number, result.outcome, result.observed, result.records, result.stop_reason,
                     account, cost or None, result.vision_used)
