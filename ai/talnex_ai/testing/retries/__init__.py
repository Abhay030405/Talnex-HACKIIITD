"""The never-blame ladder (architecture section 11).

A claim is only ever marked BROKEN when all of these hold:
  1. the page really loaded (a free Fetch check),
  2. it's still failing after waiting about a minute (free hosting often sleeps),
  3. a second try, built a different way, also fails,
  4. an independent check of the screenshots agrees it failed.
Anything else that goes wrong is "could not test" (left out of scores), never a mark against the team.

A try that could not finish because of US (it ran out of time or actions, or could not show a part of the claim)
is not a failure of the site: it gets one more try, built a different way, and if that also can't finish the
claim is "could not test". It is never "partly works" because of our own test.

When the plan splits the claim into checks, both the run and the independent check mark each one, and the
verdict comes from those marks (scoring/claim_points).

This module is a plain state machine. Everything it needs (Fetch, the runner, the planner, the proof
checker, sleeping) is passed in, so every branch can be tested with fakes and no money is spent.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from talnex_ai.formats import Result, TestPlan
from talnex_ai.safety.site_rules import LimitReached
from talnex_ai.scoring.claim_points import Decision, Evidence, decide
from talnex_ai.testing.proof_check import ProofCheck
from talnex_ai.testing.runner.runner import RunRecord
from talnex_ai.tinyfish.client import FetchResult

log = logging.getLogger("talnex.ladder")

# Why a try stopped short through no fault of the site.
INCOMPLETE_REASONS = ("ran out of time", "ran out of actions", "the test could not show every part of the claim")


@dataclass
class LadderDeps:
    fetch: Callable[[str], FetchResult]                   # is the page alive? (free)
    run: Callable[[TestPlan], RunRecord]                  # one try; raises LimitReached when out of tries
    alternate: Callable[[TestPlan, RunRecord], TestPlan]  # the same test built a different way
    check: Callable[[RunRecord, TestPlan], ProofCheck]    # the independent look at the screenshots
    sleep: Callable[[float], None] = time.sleep
    wait_seconds: int = 60
    on_trace: Optional[Callable[[str], None]] = None  # each rung as it happens, for the live view


@dataclass
class LadderResult:
    decision: Decision
    evidence: Optional[Evidence]
    runs: list[RunRecord] = field(default_factory=list)
    checks: list[ProofCheck] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)  # the ladder, step by step, in plain words
    proof_keys: list[str] = field(default_factory=list)
    second_check_agreed: Optional[bool] = None


def _keys(*runs: RunRecord) -> list[str]:
    return [s.proof_key for r in runs for s in r.steps if s.proof_key]


def incomplete(run: RunRecord) -> bool:
    """The try stopped short because of the test, not the site."""
    return run.outcome == "blocked" and (run.stop_reason or "") in INCOMPLETE_REASONS


def part_marks(run: RunRecord, check: ProofCheck, plan: TestPlan) -> dict:
    """The per-check marks for the evidence, when both judges marked every check of the plan. The ladder serves
    every runner (live browser or sandbox HTTP), and a plan without checks is judged as a whole."""
    plan_checks = getattr(plan, "checks", None) or ()
    run_parts, check_parts = getattr(run, "parts", ()) or (), getattr(check, "parts", ()) or ()
    if plan_checks and len(run_parts) == len(check_parts) == len(plan_checks):
        return {"agent_parts": tuple(run_parts), "checker_parts": tuple(check_parts),
                "part_names": tuple(c.text for c in plan_checks),
                "part_promises": tuple(getattr(c, "promise", True) for c in plan_checks)}
    return {}


def judge_claim(plan: TestPlan, site_url: str, deps: LadderDeps) -> LadderResult:
    trace: list[str] = []
    runs: list[RunRecord] = []
    checks: list[ProofCheck] = []

    def say(line: str) -> None:
        trace.append(line)
        if deps.on_trace is not None:
            try:
                deps.on_trace(line)
            except Exception as err:  # watching must never change what's being watched
                log.warning("ladder trace event failed: %s", err)

    def could_not_test(reason: str) -> LadderResult:
        say(f"Stopped: {reason}")
        return LadderResult(Decision("could_not_test", "low", reason), None, runs, checks, trace, _keys(*runs[-1:]))

    def judged(evidence: Evidence, deciding: list[RunRecord], check: ProofCheck, note: str = "") -> LadderResult:
        decision = decide(evidence)
        if note and decision.verdict != "could_not_test":
            decision = Decision(decision.verdict, decision.confidence, f"{note}; {decision.reason}")
        say(f"Result: {decision.verdict} ({decision.confidence}): {decision.reason}")
        return LadderResult(decision, evidence, runs, checks, trace, _keys(*deciding), check.outcome == evidence.agent)

    def checked(run: RunRecord, run_plan: TestPlan, label: str) -> ProofCheck:
        check = deps.check(run, run_plan)
        checks.append(check)
        say(f"{label}: {check.outcome}")
        return check

    def try_again(previous_plan: TestPlan, previous: RunRecord) -> tuple[Optional[TestPlan], Optional[RunRecord], Optional[str]]:
        """A second try, built a different way. (plan, run, None), or (None, None, why it could not be made)."""
        try:
            second_plan = deps.alternate(previous_plan, previous)
            second = deps.run(second_plan)
        except LimitReached as err:
            return None, None, f"a run limit was reached before a second try ({err})"
        except Exception as err:  # couldn't even prepare a second try: never a reason to blame the site
            log.warning("second try could not be prepared: %s", err)
            return None, None, "a second, different try could not be prepared"
        runs.append(second)
        return second_plan, second, None

    def judge_success(run: RunRecord, run_plan: TestPlan, tries: int, note: str = "") -> LadderResult:
        check = checked(run, run_plan, "Independent check")
        return judged(Evidence(run.outcome, check.outcome, tries=tries, repeat_agrees=False if tries > 1 else None,
                               screenshot_clear=check.screenshot_clear, **part_marks(run, check, run_plan)),
                      [run], check, note=note)

    def climb(failed_plan: TestPlan, failed: RunRecord) -> LadderResult:
        """A try failed. Climb the ladder before blaming anyone."""
        # 2. Wait in case the site was asleep, then make sure it's awake.
        say(f"Step 2: waiting {deps.wait_seconds}s in case the site was asleep")
        deps.sleep(deps.wait_seconds)
        page = deps.fetch(site_url)
        if not page.ok:
            return could_not_test(f"the page stopped loading when we looked again ({page.error_code or 'no answer'})")
        # 3. A second try, built a different way.
        second_plan, second, problem = try_again(failed_plan, failed)
        if problem:
            return could_not_test(problem)
        say(f"Try {len(runs)} (a different way): {second.outcome}")
        if second.outcome == "blocked":
            return could_not_test(second.stop_reason or second.observed or "the second try was blocked")
        if second.outcome in ("works", "partly_works"):
            return judge_success(second, second_plan, tries=len(runs),
                                 note="it failed once but worked on a retry, so it is not broken")
        # 4. Both tries failed: the independent check must agree before the word "broken" is used.
        check = checked(second, second_plan, "Step 4: independent check of the screenshots")
        return judged(Evidence("broken", check.outcome, tries=len(runs), repeat_agrees=True,
                               screenshot_clear=check.screenshot_clear, ladder_cleared=True,
                               **part_marks(second, check, second_plan)),
                      [failed, second], check)

    # 1. Did the page load at all?
    page = deps.fetch(site_url)
    if not page.ok:
        return could_not_test(f"the page did not load ({page.error_code or 'no answer'}), so nothing could be tried")
    say("Step 1: the page loads")

    try:
        first = deps.run(plan)
    except LimitReached as err:
        return could_not_test(f"a run limit was reached ({err})")
    runs.append(first)
    say(f"Try 1: {first.outcome}")

    if incomplete(first):
        # Our test stopped short: one more try, a different way, before giving up. Nothing here blames the site.
        say(f"Try 1 could not finish ({first.stop_reason}); trying once more a different way")
        second_plan, second, problem = try_again(plan, first)
        if problem:
            return could_not_test(problem)
        say(f"Try 2 (a different way): {second.outcome}")
        if second.outcome in ("works", "partly_works"):
            return judge_success(second, second_plan, tries=2)
        if second.outcome == "broken":  # the site failed now that the test could finish: climb the full ladder
            return climb(second_plan, second)
        return could_not_test(second.stop_reason or second.observed or "the test could not finish twice")
    if first.outcome == "blocked":
        return could_not_test(first.stop_reason or first.observed or "the test was blocked")
    if first.outcome in ("works", "partly_works"):
        return judge_success(first, plan, tries=1)
    return climb(plan, first)



def to_result(claim_id: str, ladder: LadderResult) -> Result:
    """The saved result for a claim, with the reason and the proof."""
    d = ladder.decision
    seen = ladder.checks[-1].seen if ladder.checks else ""
    reason = f"{d.reason}. The independent check saw: {seen}" if seen else d.reason
    return Result(claim_id=claim_id, verdict=d.verdict, confidence=d.confidence, reason=reason[:1000],
                  proof_keys=ladder.proof_keys, second_check_agreed=ladder.second_check_agreed if ladder.checks else None)
