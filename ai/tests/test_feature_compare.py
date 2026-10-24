import uuid

import pytest

from talnex_ai.scoring import feature_compare as fc
from talnex_ai.scoring.feature_compare import Entry, best_by_group, best_teams, eligible, group_by_meaning, order_key
from talnex_ai.worker.handlers.feature_compare import compare_event
from tests.fakes import ScriptedModel


def entry(cid, pid, verdict="works", score=8.0, steps=4, text="Add todos"):
    return Entry(cid, pid, f"Team {pid}", "Core", text, verdict, "high", score, steps)


def test_order_is_plain_code_verdict_then_score_then_steps_then_id():
    ranked = sorted([entry("c4", "p4", "reviewed_from_code", 9.0), entry("c3", "p3", "partly_works", 5.0),
                     entry("c2", "p2", "works", 8.0, steps=6), entry("c1", "p1", "works", 8.0, steps=3),
                     entry("c0", "p0", "works", 9.5)], key=order_key)
    assert [e.claim_id for e in ranked] == ["c0", "c1", "c2", "c3", "c4"]


def test_only_tested_claims_from_well_covered_teams_are_compared():
    entries = [entry("c1", "p1"), entry("c2", "p2", "broken"), entry("c3", "p3", "could_not_test"), entry("c4", "p4")]
    assert [e.claim_id for e in eligible(entries, {"p1": 80, "p2": 90, "p3": 90, "p4": 40})] == ["c1"]


def test_grouping_uses_only_valid_answers():
    entries = [entry("a1", "p1"), entry("a2", "p1", score=9.0), entry("b1", "p2"), entry("c1", "p3", text="Login")]
    model = ScriptedModel({"features": [{"name": "Add todo items", "claims": [1, 2, 3, 3, 99]},
                                        {"name": "Login", "claims": [3, 4]}]})
    groups = group_by_meaning(model, entries)
    assert len(groups) == 1  # "Login" is left with one team once 3 is used, so it's dropped
    name, members = groups[0]
    assert name == "Add todo items" and [m.claim_id for m in members] == ["a2", "b1"]  # p1's best entry only
    assert model.calls[0]["temperature"] == 0.0 and "team 1" in model.user_text(0)


def test_the_same_feature_split_across_chunks_is_joined(monkeypatch):
    monkeypatch.setattr(fc, "MAX_ENTRIES_PER_CALL", 2)
    entries = [entry("a1", "p1"), entry("x", "p9", text="Other"), entry("b1", "p2"), entry("y", "p8", text="Other 2")]
    model = ScriptedModel({"features": [{"name": "Add todo items", "claims": [1]}]},
                          {"features": [{"name": "add  TODO items", "claims": [1]}]})
    groups = group_by_meaning(model, entries)
    assert [(n, [m.claim_id for m in ms]) for n, ms in groups] == [("Add todo items", ["a1", "b1"])]


def test_best_teams_is_a_top_three_never_a_winner():
    best = best_teams([entry(f"c{i}", f"p{i}", score=float(i)) for i in range(5)]
                      + [entry("r", "pr", "reviewed_from_code", 9.9)])
    assert [b["claim_id"] for b in best] == ["c4", "c3", "c2"] and len(best) == 3
    assert best_teams([entry("r", "pr", "reviewed_from_code", 7.0)])[0]["label"] == "reviewed from code, not run"


def test_best_by_group_needs_two_well_covered_teams():
    scores = {"Core": {"p1": (80.0, 90.0), "p2": (95.0, 60.0), "p3": (99.0, 20.0)}, "Logic": {"p1": (70.0, 100.0)}}
    out = best_by_group(scores, {"p1": "A", "p2": "B", "p3": "C"})
    assert out == [("Best Core", [{"project_id": "p2", "team_name": "B", "group": "Core", "score": 95.0, "coverage": 60.0},
                                  {"project_id": "p1", "team_name": "A", "group": "Core", "score": 80.0, "coverage": 90.0}])]


@pytest.fixture
def event(pool):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event_id = conn.execute("""INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
                                   VALUES (%s, 'pytest event', 'open_theme', now() - interval '1 day', now())
                                   RETURNING id::text""", (user,)).fetchone()[0]
        for team, verdict, score, coverage in (("Ants", "works", 9.0, 100), ("Bees", "partly_works", 5.0, 80),
                                               ("Cats", "works", 7.0, 30)):
            pid = conn.execute("INSERT INTO projects (event_id, team_name) VALUES (%s, %s) RETURNING id",
                               (event_id, team)).fetchone()[0]
            cid = conn.execute("""INSERT INTO claims (project_id, text, claim_group, importance, source)
                                  VALUES (%s, %s, 'Core', 3, 'video') RETURNING id""", (pid, f"{team} add todos")).fetchone()[0]
            conn.execute("""INSERT INTO results (claim_id, verdict, confidence, reason, feature_score)
                            VALUES (%s, %s, 'high', 'seen', %s)""", (cid, verdict, score))
            for group, value in (("talnex", score * 10), ("Core", score * 10)):
                conn.execute("""INSERT INTO scores (project_id, score_group, score, coverage, confidence)
                                VALUES (%s, %s, %s, %s, 'high')""", (pid, group, value, coverage))
    yield event_id
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_compare_event_saves_feature_and_group_bests(pool, event):
    model = ScriptedModel({"features": [{"name": "Add todo items", "claims": [1, 2]}]})
    out = compare_event(pool, model, event)
    assert (out["teams"], out["features"], out["group_bests"]) == (2, 1, 1)  # Cats has too little coverage
    with pool.connection() as conn:
        rows = conn.execute("SELECT kind, feature_name, best_teams FROM feature_groups WHERE event_id = %s ORDER BY kind",
                            (event,)).fetchall()
    assert [(k, n, [b["team_name"] for b in best]) for k, n, best in rows] == [
        ("feature", "Add todo items", ["Ants", "Bees"]), ("group", "Best Core", ["Ants", "Bees"])]
    compare_event(pool, ScriptedModel({"features": [{"name": "Add todo items", "claims": [1, 2]}]}), event)
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) FROM feature_groups WHERE event_id = %s", (event,)).fetchone()[0] == 2


def test_an_event_with_one_comparable_team_is_skipped(pool, event):
    with pool.connection() as conn:
        conn.execute("""UPDATE scores SET coverage = 10 FROM projects p
                         WHERE p.id = scores.project_id AND p.team_name = 'Bees'""")
    assert compare_event(pool, ScriptedModel(), event)["skipped"]
