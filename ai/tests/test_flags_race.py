import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from talnex_ai.scoring.flags.store import add_flag

HIDDEN = "Hidden text aimed at an AI checker was found on the live site"


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event = conn.execute(
            """INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
               VALUES (%s, 'pytest event', 'open_theme', now() - interval '1 day', now()) RETURNING id""",
            (user,)).fetchone()[0]
        project_id = conn.execute("INSERT INTO projects (event_id, team_name) VALUES (%s, 'Team A') RETURNING id::text",
                                  (event,)).fetchone()[0]
    yield project_id
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def flags(pool, project_id):
    with pool.connection() as conn:
        return conn.execute("SELECT flag_type, level, reason, evidence FROM flags WHERE project_id = %s ORDER BY reason",
                            (project_id,)).fetchall()


def test_the_same_flag_found_by_many_claims_at_once_is_saved_once(pool, project):
    with ThreadPoolExecutor(max_workers=8) as workers:
        added = list(workers.map(
            lambda _: add_flag(pool, "project", project, "hidden_ai_instructions", "strong", HIDDEN,
                               {"kind": "hidden_order"}),
            range(16)))
    assert added.count(True) == 1
    assert len(flags(pool, project)) == 1


def test_different_flags_are_all_kept(pool, project):
    assert add_flag(pool, "project", project, "required_item_missing", "info", "No repository link")
    assert add_flag(pool, "project", project, "required_item_missing", "info", "No live link")
    assert not add_flag(pool, "project", project, "required_item_missing", "info", "No live link")
    assert [r[2] for r in flags(pool, project)] == ["No live link", "No repository link"]


def test_a_stronger_finding_raises_the_level_but_a_weaker_one_does_not_lower_it(pool, project):
    assert add_flag(pool, "project", project, "hidden_ai_instructions", "review", HIDDEN, {"seen": "visible"})
    assert add_flag(pool, "project", project, "hidden_ai_instructions", "strong", HIDDEN, {"seen": "hidden"})
    assert not add_flag(pool, "project", project, "hidden_ai_instructions", "info", HIDDEN, {"seen": "other"})
    assert flags(pool, project) == [("hidden_ai_instructions", "strong", HIDDEN, {"seen": "hidden"})]


def test_unknown_levels_are_refused(pool, project):
    with pytest.raises(ValueError, match="unknown flag level"):
        add_flag(pool, "project", project, "x", "critical", "nope")
