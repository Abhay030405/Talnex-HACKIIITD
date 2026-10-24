import json
import uuid
from dataclasses import dataclass

import pytest

from talnex_ai.formats import Result
from talnex_ai.llm.structured import StructuredError
from talnex_ai.scoring.claim_points import Evidence, decide, points
from talnex_ai.scoring.store import save_result
from talnex_ai.scoring.talnex_score import (
    ClaimOutcome, CriterionGroup, FeatureItem, PartScores, grade_feature, group_score, score_feature, talnex_score,
    weighted_total,
)
from talnex_ai.scoring.talnex_score.checklist import Checklist, Marks, mark_checklist, reason_line
from talnex_ai.scoring.talnex_score.feature import round1
from talnex_ai.worker.handlers.project_score import project_score
from talnex_ai.worker.registry import JobContext
from talnex_ai.db import jobs as queue


# ---- verdicts: the never-blame rule ----

@pytest.mark.parametrize("evidence, verdict, confidence", [
    (Evidence("works", "works", tries=2, repeat_agrees=True), "works", "high"),
    (Evidence("works", "works"), "works", "medium"),
    (Evidence("works", "works", screenshot_clear=False), "works", "medium"),
    (Evidence("works", "works", backup_method_used=True), "works", "low"),
    (Evidence("works"), "works", "low"),
    (Evidence("broken"), "could_not_test", "low"),                        # no second check: never broken
    (Evidence("broken", "broken"), "could_not_test", "low"),              # ladder not cleared: never broken
    (Evidence("broken", "broken", ladder_cleared=True), "broken", "medium"),
    (Evidence("works", "partly_works"), "partly_works", "low"),
    (Evidence("works", "broken", ladder_cleared=True), "could_not_test", "disagree"),
    (Evidence("blocked", "works"), "could_not_test", "low"),
])
def test_verdicts_follow_the_never_blame_rule(evidence, verdict, confidence):
    d = decide(evidence)
    assert (d.verdict, d.confidence) == (verdict, confidence) and d.reason


# ---- group scores (the worked example from architecture section 14) ----

def test_group_score_worked_example():
    g = group_score([ClaimOutcome(3, "works", "high"), ClaimOutcome(3, "partly_works", "medium"),
                     ClaimOutcome(1, "could_not_test", "low")])
    assert (g.score, g.coverage, g.claims_used, g.low_coverage) == (75.0, 66.7, 2, False)
    assert g.confidence == "high"  # (1.0 + 0.6) / 2 = 0.8


def test_untested_claims_never_count_against_anyone():
    g = group_score([ClaimOutcome(3, "could_not_test", "low"), ClaimOutcome(2, "works", "disagree"),
                     ClaimOutcome(1, "works", "high", testable=False)])
    assert g.score is None and g.coverage == 0.0 and g.low_coverage


def test_reviewed_from_code_counts_by_its_feature_score():
    assert group_score([ClaimOutcome(2, "reviewed_from_code", "low", points_override=0.6)]).score == 60.0
    assert group_score([ClaimOutcome(2, "reviewed_from_code", "low")]).score is None


def test_weighted_total_rescales_over_scored_criteria():
    scored = group_score([ClaimOutcome(1, "works", "high")])
    total = weighted_total([CriterionGroup(3, scored), CriterionGroup(1, group_score([]))])
    assert (total.score, total.weight_covered, total.criteria_used, total.criteria_total) == (100.0, 75.0, 1, 2)
    assert weighted_total([CriterionGroup(1, group_score([]))]).score is None


# ---- feature scores out of 10 ----

def test_feature_score_weights_by_role_and_rescales_missing_parts():
    parts = PartScores(implementation=1.0, logic=0.5, edge=0.0, design=1.0)
    assert score_feature("works", parts, "fresher").score == 6.8   # (50*1 + 35*.5 + 15*0) / 100 * 10 = 6.75
    assert score_feature("works", parts, "senior").score == 6.3    # 30 + 12.5 + 0 + 20
    only_impl = score_feature("works", PartScores(implementation=0.8), "fresher")
    assert only_impl.score == 8.0 and only_impl.weights_used == {"implementation": 100.0}
    assert only_impl.unmeasured == ("logic", "edge")


def test_caps_and_zero_cases():
    full = PartScores(implementation=1.0, logic=1.0, edge=1.0, design=1.0)
    assert score_feature("partly_works", full, "mid").score == 5.0
    assert score_feature("reviewed_from_code", full, "mid").score == 7.0
    assert score_feature("broken", full, "mid").zero_reason == "tested and not working"
    assert score_feature("works", full, "mid", mechanism_missing=True).score == 0.0
    assert score_feature("could_not_test", full, "mid").score is None
    assert score_feature("works", PartScores(), "mid").score is None


def test_rounding_is_half_up():
    assert round1(6.75) == 6.8 and round1(2.25) == 2.3


def test_talnex_score_is_importance_weighted_and_skips_unscored():
    t = talnex_score([FeatureItem(3, 8.0, confidence="high"), FeatureItem(1, 4.0, confidence="medium"),
                      FeatureItem(2, None), FeatureItem(1, None, testable=False)])
    assert (t.score10, t.stored, t.coverage, t.features_used, t.low_coverage) == (7.0, 70.0, 66.7, 2, False)
    assert talnex_score([]).score10 is None


# ---- checklist grading with a fake model ----

@dataclass
class Reply:
    text: str
    truncated: bool = False


class FakeModel:
    def __init__(self, *answers):
        self.answers = [json.dumps(a) if not isinstance(a, str) else a for a in answers]
        self.roles = []

    def chat(self, role, messages, **options):
        self.roles.append(role)
        return Reply(self.answers.pop(0))


CHECKLIST = {"items": [{"text": "search returns results", "part": "implementation", "core": True},
                       {"text": "results match the query", "part": "logic"},
                       {"text": "empty query handled", "part": "edge"}]}


def marks(*statuses, present=None):
    return {"marks": [{"index": i, "status": s, "note": "step 2"} for i, s in enumerate(statuses, 1)],
            "mechanism_present": present}


def test_grade_a_working_feature():
    model = FakeModel(CHECKLIST, marks("present", "present", "missing"))
    grade = grade_feature(model, "Search recipes", "Core", "fresher", "works", "typed 'egg', saw 4 egg recipes")
    assert grade.score == 8.5  # (50 + 35 + 0) / 100 * 10
    assert grade.reason.startswith("8.5/10 for fresher: + search returns results; results match the query - empty query")
    assert model.roles == ["claim_reader", "proof_checker"]
    assert grade.breakdown["parts"]["edge"] == 0.0


def test_seen_working_is_never_zeroed_by_a_doubtful_marker():
    model = FakeModel(CHECKLIST, marks("missing", "unknown", "unknown", present=False))
    grade = grade_feature(model, "Search", "Core", "fresher", "works", "it worked")
    assert grade.breakdown["zero_reason"] is None and "not implemented" not in grade.reason
    model = FakeModel(CHECKLIST, marks("missing", "unknown", "unknown", present=False))
    from_code = grade_feature(model, "Search", "Core", "fresher", "reviewed_from_code", "no search code")
    assert from_code.score == 0.0 and "not implemented" in from_code.reason


def test_no_model_needed_for_untested_or_broken():
    model = FakeModel()
    assert grade_feature(model, "x", "Core", "mid", "could_not_test", "").score is None
    assert grade_feature(model, "x", "Core", "mid", "broken", "").reason == "0/10 for mid: tested and not working"
    assert model.roles == []


def test_marks_out_of_order_are_accepted_but_gaps_are_not():
    checklist = Checklist.model_validate(CHECKLIST)
    out_of_order = {"marks": [{"index": 3, "status": "missing"}, {"index": 1, "status": "present"},
                              {"index": 2, "status": "unknown"}]}
    got = mark_checklist(FakeModel(out_of_order), checklist, "x", "e")
    assert [m.index for m in got.marks] == [1, 2, 3]
    with pytest.raises(StructuredError, match="numbered 1 to 3"):
        mark_checklist(FakeModel(marks("present"), marks("present")), checklist, "x", "e")


def test_checklist_needs_a_core_implementation_item():
    with pytest.raises(ValueError, match="core item"):
        Checklist.model_validate({"items": [{"text": "aaa", "part": "logic"}] * 3})


def test_reason_line_notes_caps_and_code_review():
    checklist = Checklist.model_validate(CHECKLIST)
    m = Marks.model_validate(marks("present", "present", "present"))
    assert reason_line(7.0, "mid", checklist, m, capped_note="capped at 7", reviewed_only=True).endswith(
        "(capped at 7; reviewed from code, not run)")
    assert reason_line(None, "mid", checklist, m) == "not scored: there was not enough evidence"


# ---- the project_score stage, with a real database ----

@pytest.fixture
def fixed_project(pool):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event = conn.execute(
            """INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
               VALUES (%s, 'pytest event', 'fixed_problem', now() - interval '1 day', now()) RETURNING id""",
            (user,)).fetchone()[0]
        conn.execute("INSERT INTO criteria (event_id, name, weight) VALUES (%s, 'Search', 3), (%s, 'Sharing', 1)",
                     (event, event))
        project = conn.execute("INSERT INTO projects (event_id, team_name) VALUES (%s, 'Team A') RETURNING id::text",
                               (event,)).fetchone()[0]
        claim_ids = [conn.execute(
            """INSERT INTO claims (project_id, text, claim_group, importance, source)
               VALUES (%s, %s, %s, %s, 'criteria') RETURNING id::text""", (project, text, group, imp)).fetchone()[0]
                     for text, group, imp in (("search works", "Search", 3), ("filters work", "Search", 1),
                                              ("share a link", "Sharing", 2))]
    yield project, claim_ids
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_project_score_stage(pool, fixed_project):
    project, (search, filters, share) = fixed_project
    save_result(pool, Result(claim_id=search, verdict="works", confidence="high", reason="seen", proof_keys=["s/1"]))
    save_result(pool, Result(claim_id=filters, verdict="partly_works", confidence="medium", reason="seen"))
    save_result(pool, Result(claim_id=filters, verdict="works", confidence="medium", reason="re-run"))  # replaces
    queue.enqueue_job(pool, "project_score", "python", "project", project, pipeline="hackathon")
    job = queue.take_job(pool, "python", "w")

    result = project_score(job, JobContext(job, pool))
    assert result["groups"] == {"Search": 100.0, "Sharing": None}
    assert result["not_tested"] == ["share a link"]
    assert result["weighted_total"] == {"score": 100.0, "weight_covered": 75.0, "criteria_used": 1, "criteria_total": 2}
    with pool.connection() as conn:
        assert conn.execute("SELECT status FROM projects WHERE id = %s", (project,)).fetchone()[0] == "done_with_gaps"
        rows = dict(conn.execute("SELECT score_group, score FROM scores WHERE project_id = %s", (project,)).fetchall())
    assert float(rows["Search"]) == 100.0 and rows["Sharing"] is None and float(rows["weighted_total"]) == 100.0
