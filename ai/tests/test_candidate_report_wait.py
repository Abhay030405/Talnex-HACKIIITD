"""The candidate report waits for the coding checks of the same run before it is built."""
from types import SimpleNamespace

from talnex_ai.worker.handlers import candidate_report as stage


class Ctx:
    def __init__(self, remaining=600.0):
        self.pool, self._remaining = None, remaining

    def remaining(self):
        return self._remaining

    def check(self):
        pass


JOB = SimpleNamespace(target_id="c1", run_number=2)


def test_it_waits_until_the_coding_checks_finish(monkeypatch):
    counts, asked, slept = iter([2, 1, 0]), [], []
    monkeypatch.setattr(stage, "coding_still_running", lambda pool, cid, run: asked.append((cid, run)) or next(counts))
    assert stage.wait_for_coding(JOB, Ctx(), 480, sleep=slept.append) == 0
    assert asked == [("c1", 2)] * 3 and slept == [stage.POLL_SECONDS] * 2


def test_it_stops_waiting_at_the_limit_and_reports_what_is_still_running(monkeypatch):
    clock = iter(range(0, 10_000, 100))
    monkeypatch.setattr(stage.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(stage, "coding_still_running", lambda *a: 1)
    assert stage.wait_for_coding(JOB, Ctx(), 300, sleep=lambda s: None) == 1


def test_nothing_running_means_no_wait(monkeypatch):
    monkeypatch.setattr(stage, "coding_still_running", lambda *a: 0)
    slept = []
    assert stage.wait_for_coding(JOB, Ctx(), 480, sleep=slept.append) == 0 and slept == []
