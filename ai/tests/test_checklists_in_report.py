"""What TalNex planned to check per claim reaches the report: from test_plan (live) and sandbox_plan (backend)."""
from talnex_ai.reports.proof import checklists


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        assert "test_plan" in sql and params == ("candidate_project", "p1")
        return self

    def fetchall(self):
        return self.rows


def item(text):
    return {"text": text, "part": "implementation", "core": True}


def test_checklists_come_from_both_plans_and_later_runs_win():
    rows = [
        ("test_plan", {"claims": {"c1": {"checklist": {"items": [item("old item")]}}}}),
        ("sandbox_plan", {"checklists": {"c2": {"checklist": {"items": [item("POST /todos saves")]}}}}),
        ("test_plan", {"claims": {"c1": {"checklist": {"items": [item("Todo appears in list"), {"part": "x"}]}},
                                  "c3": {"plans": []}}}),
    ]
    assert checklists(FakeConn(rows), "candidate_project", "p1") == {
        "c1": ["Todo appears in list"], "c2": ["POST /todos saves"]}


def test_no_plans_means_no_checklists():
    assert checklists(FakeConn([("test_plan", None)]), "candidate_project", "p1") == {}
