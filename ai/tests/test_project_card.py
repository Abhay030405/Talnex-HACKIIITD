import uuid

import pytest

from talnex_ai.db import jobs as queue
from talnex_ai.reports.project_card import OPINION_LABEL, build_project_card
from talnex_ai.worker.handlers.project_report import save_card, start_event_checks


@pytest.fixture
def hackathon(pool):
    """A fixed-problem event with two teams. Team A has a tested claim, an untested one, scores, a flag and an opinion."""
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event = conn.execute("""INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
                                VALUES (%s, 'Pytest Hack', 'fixed_problem', now() - interval '1 day', now()) RETURNING id::text""",
                             (user,)).fetchone()[0]
        conn.execute("INSERT INTO criteria (event_id, name, description, weight) VALUES (%s, 'Speed', 'fast', 1), (%s, 'Search', NULL, 3)",
                     (event, event))
        a = conn.execute("""INSERT INTO projects (event_id, team_name, live_url, repo_url)
                            VALUES (%s, 'Ants', 'https://ants.test', 'https://github.com/a/b') RETURNING id::text""",
                         (event,)).fetchone()[0]
        b = conn.execute("INSERT INTO projects (event_id, team_name) VALUES (%s, 'Bees') RETURNING id::text", (event,)).fetchone()[0]
        tested = conn.execute("""INSERT INTO claims (project_id, text, claim_group, importance, source)
                                 VALUES (%s, 'Search recipes', 'Search', 3, 'criteria') RETURNING id""", (a,)).fetchone()[0]
        conn.execute("""INSERT INTO claims (project_id, text, claim_group, importance, source)
                        VALUES (%s, 'Share a list', 'Core', 1, 'video')""", (a,))
        conn.execute("""INSERT INTO results (claim_id, verdict, confidence, reason, feature_score, score_reason)
                        VALUES (%s, 'works', 'high', 'seen', 8.5, '8.5/10 for fresher')""", (tested,))
        for group, score, coverage in (("Search", 100, 100), ("Core", None, 0), ("talnex", 85, 50), ("weighted_total", 100, 75)):
            conn.execute("""INSERT INTO scores (project_id, score_group, score, coverage, confidence)
                            VALUES (%s, %s, %s, %s, 'high')""", (a, group, score, coverage))
        conn.execute("""INSERT INTO flags (project_id, flag_type, level, reason)
                        VALUES (%s, 'hidden_ai_instructions', 'strong', 'Hidden text aimed at an AI checker')""", (a,))
        conn.execute("""INSERT INTO opinions (project_id, kind, parts, models)
                        VALUES (%s, 'innovation', '[{"name": "idea", "disagree": true}]', '{m1,m2}')""", (a,))
    yield event, a, b
    with pool.connection() as conn:
        conn.execute("DELETE FROM jobs WHERE target_id IN (%s, %s, %s)", (a, b, event))
        conn.execute("DELETE FROM events WHERE id = %s", (event,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_the_card_shows_proof_and_gaps_and_never_ranks(pool, hackathon):
    _, a, _ = hackathon
    card = build_project_card(pool, a)
    assert card["team_name"] == "Ants" and card["event"]["mode"] == "fixed_problem"
    assert [c["name"] for c in card["criteria"]] == ["Search", "Speed"]                # heaviest first
    assert [g["group"] for g in card["groups"]] == ["Search", "Speed", "Core"]        # criteria first, unscored ones too
    assert card["groups"][1] == {"group": "Speed", "kind": "criterion", "score": None, "coverage": 0.0,
                                 "confidence": None, "claims_used": 0, "low_coverage": True}
    assert card["talnex"] == {"score10": 8.5, "coverage": 50.0, "confidence": "high", "features_scored": 1,
                              "features_total": 2, "low_coverage": False}
    assert card["weighted_total"]["label"] == "based on your criteria and tested claims only"
    assert card["flags"][0]["level"] == "strong" and card["has_gaps"]
    assert any("could not be tested" in n for n in card["notes"]) and any("No team is ranked" in n for n in card["notes"])
    assert card["ai_opinion"]["label"] == OPINION_LABEL and card["ai_opinion"]["innovation"]["disagreement_note"]
    assert "screens" in card["ai_opinion"]["ui_note"] or "screenshots" in card["ai_opinion"]["ui_note"]
    assert card["sandbox"] == {"ran": False, "reason": "no repository was run in a sandbox"}


def test_a_failed_or_skipped_stage_is_listed(pool, hackathon):
    _, a, _ = hackathon
    queue.enqueue_job(pool, "video_read", "python", "project", a, pipeline="hackathon")
    job = queue.take_job(pool, "python", "w")
    queue.complete_job(pool, job.id, "w", {"skipped": True, "reason": "no demo video was given"})
    assert {"stage": "video_read", "status": "skipped", "reason": "no demo video was given"} in build_project_card(pool, a)["checks"]


def test_saving_twice_replaces_the_card(pool, hackathon):
    _, a, _ = hackathon
    save_card(pool, a)
    save_card(pool, a)
    with pool.connection() as conn:
        rows = conn.execute("SELECT report->>'team_name', has_gaps FROM project_reports WHERE project_id = %s", (a,)).fetchall()
    assert rows == [("Ants", True)]
    with pytest.raises(LookupError):
        build_project_card(pool, str(uuid.uuid4()))


def test_event_checks_start_only_when_every_team_has_its_report(pool, hackathon):
    event, a, b = hackathon
    for project in (a, b):
        queue.enqueue_job(pool, "project_report", "python", "project", project, pipeline="hackathon")
    queue.take_job(pool, "python", "w")  # one team's report is running, the other still queued
    assert start_event_checks(pool, a) is False
    queue.take_job(pool, "python", "w")
    started = start_event_checks(pool, a)
    with pool.connection() as conn:
        event_jobs = conn.execute("SELECT count(*) FROM jobs WHERE target_id = %s AND pipeline = 'hackathon_event'",
                                  (event,)).fetchone()[0]
    assert started is True and event_jobs >= 1
    assert start_event_checks(pool, b) is False  # starting again adds nothing
