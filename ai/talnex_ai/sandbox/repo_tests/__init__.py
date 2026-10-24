"""Run the repository's own tests inside the VM and read how many passed (architecture 28.7, "Repo's own tests").

The pass count is evidence for the Reliability group (importance 1), never proof on its own: a repo's tests may need a
database or a key the sandbox does not have, so tests that all fail here are "could not confirm", not a mark against the team.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Frameworks print their totals in different ways. Each reader returns (passed, failed) or None when the text is not its own.


@dataclass(frozen=True)
class TestCounts:
    __test__ = False  # not a pytest test class, despite the name

    passed: int
    failed: int
    framework: str

    @property
    def total(self) -> int:
        return self.passed + self.failed


def _int(m: Optional[re.Match], group: str) -> int:
    return int(m.group(group)) if m and m.group(group) else 0


def parse_test_output(text: str) -> Optional[TestCounts]:
    """Counts from the end of a test run's output, or None when no known framework's summary is found."""
    tail = text[-6000:]

    # pytest: "=== 2 failed, 10 passed, 1 skipped in 3.2s ===" or "10 passed in 1s"
    if re.search(r"\b(passed|failed)\b.* in [\d.]+s", tail) or "pytest" in tail.lower():
        passed = sum(int(n) for n in re.findall(r"(\d+) passed", tail))
        failed = sum(int(n) for n in re.findall(r"(\d+) (?:failed|error)", tail))
        if passed or failed:
            return TestCounts(passed, failed, "pytest")

    # jest / vitest: "Tests:       1 failed, 4 passed, 5 total"
    m = re.search(r"Tests:\s+(?:(?P<failed>\d+) failed,\s*)?(?:(?P<skipped>\d+) skipped,\s*)?(?:(?P<todo>\d+) todo,\s*)?(?:(?P<passed>\d+) passed,\s*)?(?P<total>\d+) total", tail)
    if m:
        return TestCounts(_int(m, "passed"), _int(m, "failed"), "jest")
    m = re.search(r"Tests\s+(?:(?P<failed>\d+) failed\s*\|\s*)?(?P<passed>\d+) passed", tail)  # vitest
    if m:
        return TestCounts(_int(m, "passed"), _int(m, "failed"), "vitest")

    # mocha: "5 passing (20ms)" and "2 failing"
    passing, failing = re.search(r"(\d+) passing", tail), re.search(r"(\d+) failing", tail)
    if passing or failing:
        return TestCounts(int(passing.group(1)) if passing else 0, int(failing.group(1)) if failing else 0, "mocha")

    # node:test (TAP): "# pass 3" and "# fail 1"
    p, f = re.search(r"^# pass (\d+)", tail, re.M), re.search(r"^# fail (\d+)", tail, re.M)
    if p:
        return TestCounts(int(p.group(1)), int(f.group(1)) if f else 0, "node:test")

    # unittest: "Ran 7 tests in 0.1s" then "OK" or "FAILED (failures=2, errors=1)"
    ran = re.search(r"Ran (\d+) tests? in", tail)
    if ran:
        bad = re.search(r"FAILED \((?:failures=(\d+))?(?:,\s*)?(?:errors=(\d+))?", tail)
        failed = (int(bad.group(1) or 0) + int(bad.group(2) or 0)) if bad else 0
        return TestCounts(int(ran.group(1)) - failed, failed, "unittest")
    return None


def describe(counts: Optional[TestCounts], exit_code: int, timed_out: bool) -> tuple[str, str]:
    """(verdict, reason) for the claim "the repository's own tests pass". Never "broken": a test run in a bare VM proves little."""
    if timed_out:
        return "could_not_test", "the repository's tests ran out of time"
    if counts is None:
        if exit_code == 0:
            return "works", "the test command finished without errors (no counts were printed)"
        return "could_not_test", f"the test command exited with {exit_code} and printed no counts we can read"
    if counts.failed == 0 and counts.passed > 0:
        return "works", f"all {counts.passed} of the repository's own tests passed ({counts.framework})"
    if counts.passed > 0:
        return "partly_works", f"{counts.passed} of {counts.total} of the repository's own tests passed ({counts.framework})"
    if counts.total > 0:
        return "could_not_test", (f"none of the repository's {counts.total} tests passed here ({counts.framework}); "
                                  "they may need a database or keys the sandbox does not have")
    return "could_not_test", "the repository has no tests that ran"
