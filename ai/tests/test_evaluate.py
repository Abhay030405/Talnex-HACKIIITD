import json
from pathlib import Path

import pytest

from talnex_ai.worker.evaluate import REPO_ROOT, ClaimRun, RunData, analyse, render_report

EXPECTED = {
    "app": "demo",
    "claims": [{"text": "Add a todo", "expected": "works"}, {"text": "Convert money", "expected": "works"}],
    "controls": [{"text": "Export a PDF", "expected": "broken"}],
    "expected_flags": 0,
    "criteria": {"verdict_agreement_runs": 2, "talnex_score_spread_max": 10},
}


def run(i, add="works", convert="works", pdf="broken", talnex=70.0, flags=(), finished=True, scores=(8.0, 8.0, 0.0)):
    r = RunData(index=i, finished=finished, talnex=talnex, flags=list(flags), seconds=100 + i, cost_usd=0.05)
    for text, v, s in (("Add a todo", add, scores[0]), ("Convert money", convert, scores[1]), ("Export a PDF", pdf, scores[2])):
        r.claims[text] = ClaimRun(v, "medium", s)
    return r


class TestAnalyse:
    def test_three_perfect_runs_pass(self):
        a = analyse(EXPECTED, [run(1), run(2), run(3)])
        assert a["passed"] and a["accuracy"] == 100.0
        assert a["pairs"] == {"correct": 9, "wrong": 0, "unconfirmed": 0, "total": 9}
        assert all(a["checks"].values())

    def test_one_odd_verdict_in_three_runs_is_still_steady_but_counts_as_wrong(self):
        a = analyse(EXPECTED, [run(1), run(2, add="broken"), run(3)])
        claim = next(c for c in a["claims"] if c["claim"] == "Add a todo")
        assert claim["steady"] and claim["majority"] == "works" and claim["agreeing_runs"] == 2
        assert a["pairs"]["wrong"] == 1 and a["checks"]["no wrong verdicts"] is False and not a["passed"]

    def test_could_not_test_is_unconfirmed_never_wrong(self):
        a = analyse(EXPECTED, [run(1), run(2, convert="could_not_test"), run(3)])
        assert a["pairs"]["wrong"] == 0 and a["pairs"]["unconfirmed"] == 1
        assert a["checks"]["no wrong verdicts"] is True and a["passed"]

    def test_a_missing_result_is_unconfirmed(self):
        r2 = run(2)
        del r2.claims["Convert money"]
        a = analyse(EXPECTED, [run(1), r2, run(3)])
        assert a["pairs"]["unconfirmed"] == 1 and a["pairs"]["wrong"] == 0

    def test_a_claim_with_three_different_verdicts_is_not_steady(self):
        a = analyse(EXPECTED, [run(1, add="works"), run(2, add="broken"), run(3, add="partly_works")])
        claim = next(c for c in a["claims"] if c["claim"] == "Add a todo")
        assert claim["steady"] is False and not a["passed"]

    def test_the_control_claim_must_come_out_broken(self):
        a = analyse(EXPECTED, [run(1, pdf="works"), run(2, pdf="works"), run(3, pdf="works")])
        control = next(c for c in a["claims"] if c["control"])
        assert control["majority"] == "works" and not control["majority_is_expected"] and not a["passed"]

    def test_the_talnex_score_may_move_by_ten_points_but_not_more(self):
        assert analyse(EXPECTED, [run(1, talnex=70), run(2, talnex=75), run(3, talnex=80)])["passed"]
        a = analyse(EXPECTED, [run(1, talnex=70), run(2, talnex=75), run(3, talnex=80.1)])
        assert a["talnex_spread"] == 10.1 and a["checks"]["TalNex score spread within 10 points"] is False

    def test_an_unexpected_flag_fails_the_check(self):
        a = analyse(EXPECTED, [run(1), run(2, flags=["info: no live link"]), run(3)])
        assert a["flags_per_run"] == [0, 1, 0] and a["checks"]["no unexpected red flags"] is False

    def test_a_run_that_did_not_finish_fails(self):
        assert not analyse(EXPECTED, [run(1), run(2, finished=False), run(3)])["passed"]

    def test_fewer_than_three_runs_need_every_run_to_agree(self):
        assert analyse(EXPECTED, [run(1), run(2)])["passed"]
        assert not analyse(EXPECTED, [run(1), run(2, add="broken")])["passed"]

    def test_a_single_run_is_allowed(self):
        a = analyse(EXPECTED, [run(1)])
        assert a["passed"] and a["talnex_spread"] == 0.0

    def test_numbers_for_the_report_are_collected(self):
        a = analyse(EXPECTED, [run(1), run(2), run(3)])
        assert a["seconds_per_run"] == [101, 102, 103] and a["cost_per_run"] == [0.05, 0.05, 0.05]


class TestReport:
    def test_the_report_says_pass_or_fail_with_the_reasons(self):
        good = render_report(analyse(EXPECTED, [run(1), run(2), run(3)]), "2026-10-21 12:00 UTC")
        assert "**Result: PASS**" in good and "PASS: no wrong verdicts" in good and "Export a PDF (control)" in good
        bad = render_report(analyse(EXPECTED, [run(1), run(2, add="broken"), run(3)]), "2026-10-21 12:00 UTC", "short wait")
        assert "**Result: FAIL**" in bad and "FAIL: no wrong verdicts" in bad and "short wait" in bad


class TestTheRealExpectedFile:
    def test_the_honest_app_file_is_well_formed(self):
        data = json.loads(Path(REPO_ROOT / "eval" / "expected" / "honest.json").read_text(encoding="utf-8"))
        assert data["app"] == "honest" and data["url"].startswith("https://")
        assert len(data["claims"]) >= 5 and all(c["expected"] == "works" for c in data["claims"])
        assert data["controls"] and all(c["expected"] == "broken" for c in data["controls"])
        texts = [c["text"] for c in data["claims"] + data["controls"]]
        assert len(texts) == len(set(texts))
        assert all(1 <= c.get("importance", 2) <= 3 for c in data["claims"] + data["controls"])
