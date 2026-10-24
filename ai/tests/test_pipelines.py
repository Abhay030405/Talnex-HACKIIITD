"""The pipelines are data in the database (pipeline_stages). Check their shape: every stage waits only for
stages of its own pipeline, nothing waits in a circle, and the live and sandbox tracks meet before scoring."""
import pytest

SANDBOX_TRACK = ["sandbox_run", "route_discovery", "sandbox_plan", "sandbox_test", "repo_tests", "code_review",
                 "sandbox_end", "track_reconcile"]


@pytest.fixture
def pipelines(pool):
    with pool.connection() as conn:
        rows = conn.execute("SELECT pipeline, stage, runner, target_type, after_stages FROM pipeline_stages").fetchall()
    out: dict[str, dict[str, tuple]] = {}
    for pipeline, stage, runner, target, after in rows:
        out.setdefault(pipeline, {})[stage] = (runner, target, list(after))
    return out


def test_every_stage_can_start_and_waits_only_for_its_own_pipeline(pipelines):
    assert pipelines, "no pipelines found: are the migrations applied?"
    for pipeline, table in pipelines.items():
        for stage, (_, _, after) in table.items():
            missing = [a for a in after if a not in table]
            assert not missing, f"{pipeline}.{stage} waits for {missing}, which are not in that pipeline"
        started: set[str] = set()
        while True:
            ready = {s for s, (_, _, after) in table.items() if s not in started and set(after) <= started}
            if not ready:
                break
            started |= ready
        assert started == set(table), f"{pipeline} has stages that can never start: {sorted(set(table) - started)}"


@pytest.mark.parametrize("pipeline, target", [("hackathon", "project"), ("recruiter", "candidate_project")])
def test_both_tracks_meet_before_scoring(pipelines, pipeline, target):
    table = pipelines[pipeline]
    for name in SANDBOX_TRACK:
        assert name in table and table[name][:2] == ("python", target), f"{pipeline} lacks {name}"
    assert table["feature_score"][2] == ["track_reconcile"]
    assert set(table["track_reconcile"][2]) == {"proof_check", "sandbox_end"}


def test_the_ai_opinion_runs_last_at_event_level(pipelines):
    event = pipelines["hackathon_event"]
    assert event["ai_opinion"][:2] == ("python", "event") and event["ai_opinion"][2] == ["feature_compare"]
