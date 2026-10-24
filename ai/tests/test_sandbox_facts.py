"""The VM test facts for the report: stage results kept small, no long lists."""
from talnex_ai.reports.sandbox import _plain


def test_stage_results_keep_scalars_and_small_counts_and_turn_lists_into_counts():
    got = _plain({"passed": 0, "failed": 1, "reason": "needs a database", "mechanisms": {"present": 9, "partial": 5},
                  "routes": [{"m": "GET"}, {"m": "POST"}], "nested": {"a": {"b": 1}}})
    assert got == {"passed": 0, "failed": 1, "reason": "needs a database", "mechanisms": {"present": 9, "partial": 5},
                   "routes_count": 2}
    assert _plain(None) == {} and _plain([1, 2]) == {}
