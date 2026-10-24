"""The recruiter proof report: the builder, the stage handler and the pipeline start. Real database, no models."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from talnex_ai.db import jobs as queue
from talnex_ai.reports.recruiter_report import build_report
from talnex_ai.worker.handlers import candidate_report, project_summary  # noqa: F401
from tests.test_recruiter import job_for, run

SECRET_BULLET = "SECRET-RESUME-BULLET: led a team of five at Acme Corp"


@pytest.fixture(autouse=True)
def clean(pool):
    with pool.connection() as conn:
        conn.execute("DELETE FROM jobs")
    yield


def _candidate(pool):
    with pool.connection() as conn:
        owner = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id::text",
                             (f"rep-{uuid.uuid4()}@example.com",)).fetchone()[0]
        return conn.execute(
            "INSERT INTO candidates (owner_id, label, resume_key, role_level) VALUES (%s::uuid, 'c', 'resumes/x/r.pdf', 'junior') "
            "RETURNING id::text", (owner,)).fetchone()[0]


def _project(pool, cid, name, live=None, repo=None):
    with pool.connection() as conn:
        return conn.execute(
            "INSERT INTO candidate_projects (candidate_id, name, bullets, live_url, repo_url) VALUES (%s::uuid, %s, %s, %s, %s) "
            "RETURNING id::text", (cid, name, [SECRET_BULLET], live, repo)).fetchone()[0]


def _claim(pool, pid, text, verdict=None, score=None, testable=True, importance=3, steps=()):
    with pool.connection() as conn:
        cl = conn.execute(
            "INSERT INTO claims (candidate_project_id, text, claim_group, importance, source, testable, untestable_reason) "
            "VALUES (%s::uuid, %s, 'Core', %s, 'resume', %s, %s) RETURNING id::text",
            (pid, text, importance, testable, None if testable else "needs a paid account")).fetchone()[0]
        if verdict:
            conn.execute(
                "INSERT INTO results (claim_id, verdict, confidence, reason, feature_score, score_reason) "
                "VALUES (%s::uuid, %s, 'high', 'seen on screen', %s, %s)",
                (cl, verdict, score, "why this score" if score is not None else None))
        if steps:
            run_id = conn.execute(
                "INSERT INTO test_runs (claim_id, track, test_type, started_at) VALUES (%s::uuid, 'live', 'normal', now()) "
                "RETURNING id::text", (cl,)).fetchone()[0]
            for n, (action, observed) in enumerate(steps, 1):
                conn.execute("INSERT INTO steps (run_id, step_number, kind, action, observed, proof_key) "
                             "VALUES (%s::uuid, %s, 'screen', %s, %s, %s)", (run_id, n, action, observed, f"screens/{cl}/{n}.png"))
            extra = conn.execute(
                "INSERT INTO test_runs (claim_id, track, test_type, started_at) VALUES (%s::uuid, 'live', 'bad_input', now()) "
                "RETURNING id::text", (cl,)).fetchone()[0]
            conn.execute("INSERT INTO steps (run_id, step_number, kind, action, observed) VALUES (%s::uuid, 1, 'screen', "
                         "'Type nothing and submit', 'An error message appeared')", (extra,))
    return cl


def _score(pool, pid, score, coverage):
    with pool.connection() as conn:
        conn.execute("INSERT INTO scores (candidate_project_id, score_group, score, coverage, confidence, claims_used) "
                     "VALUES (%s::uuid, 'talnex', %s, %s, 'high', 3)", (pid, score, coverage))


def _seed(pool):
    cid = _candidate(pool)
    good = _project(pool, cid, "TinyTools", "https://tiny.example.com", "https://github.com/x/tiny")
    _claim(pool, good, "Guest sign-in", "works", 10, steps=[("Open the site", "Landing page loaded"), ("Click guest", "Dashboard shown")])
    _claim(pool, good, "Dark mode", "partly_works", 6.5)
    _claim(pool, good, "Export to PDF", "broken", 0)
    _claim(pool, good, "Paid plans", "could_not_test")
    _claim(pool, good, "Needs a phone", testable=False)
    _score(pool, good, 87.5, 75)
    bare = _project(pool, cid, "ChatSummarizer", None, "https://github.com/x/chat")
    with pool.connection() as conn:
        conn.execute("INSERT INTO flags (candidate_project_id, flag_type, level, reason) VALUES (%s::uuid, 'required_item_missing', 'info', 'no README')", (good,))
        conn.execute("INSERT INTO flags (candidate_id, flag_type, level, reason) VALUES (%s::uuid, 'hidden_ai_instructions', 'review', 'hidden text')", (cid,))
        conn.execute("INSERT INTO coding_signals (candidate_id, site, signal, weight, evidence) VALUES (%s::uuid, 'leetcode', 'leetcode_profile', 'not_suspicious', '{\"a\": 1}')", (cid,))
        for pid, repo in ((good, {"found": True, "fork": False, "created_at": "2024-01-01T00:00:00Z", "pushed_at": "2024-02-01T00:00:00Z", "languages": {"Go": 100}}),
                          (bare, {"found": False, "reason": "the repository does not exist or is private"})):
            conn.execute("INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, status, result) "
                         "VALUES ('github_check', 'go', 'candidate_project', %s::uuid, 'recruiter', 'done', %s::jsonb)", (pid, json.dumps(repo)))
        conn.execute("INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, status, result) "
                     "VALUES ('originality', 'python', 'candidate_project', %s::uuid, 'recruiter', 'done', %s::jsonb)",
                     (good, json.dumps({"repo_vs_live": {"skipped": True, "reason": "no live link"},
                                        "tutorial_copy": {"checked": True, "match": "partial"}})))
    return cid, good, bare


class TestBuilder:
    def test_full_report(self, pool):
        cid, good, bare = _seed(pool)
        r = build_report(pool, cid)
        assert r["version"] == 1 and r["candidate_id"] == cid and r["role_level"] == "junior"
        assert [p["name"] for p in r["projects"]] == ["TinyTools", "ChatSummarizer"]
        p = r["projects"][0]
        assert p["status"] == "tested" and p["status_reason"] == ""
        assert p["talnex"]["score10"] == 8.8 or p["talnex"]["score10"] == 8.7  # 87.5 / 10, rounded to one place
        assert p["talnex"]["coverage"] == 75 and p["talnex"]["low_coverage"] is False
        assert p["talnex"]["features_total"] == 4 and p["talnex"]["features_scored"] == 3
        by = {f["text"]: f for f in p["features"]}
        assert by["Guest sign-in"]["verdict"] == "works" and by["Guest sign-in"]["score10"] == 10.0
        assert by["Guest sign-in"]["score_reason"] == "why this score"
        assert by["Paid plans"]["verdict"] == "could_not_test" and by["Paid plans"]["score10"] is None
        assert by["Needs a phone"]["testable"] is False and by["Needs a phone"]["untestable_reason"] and by["Needs a phone"]["verdict"] is None
        proof = by["Guest sign-in"]["proof"]
        assert [s["step"] for s in proof] == [1, 2, 3]
        assert proof[0]["action"] == "Open the site" and proof[0]["proof_key"].startswith("screens/")
        assert proof[2]["observed"] == "An error message appeared"       # the extra check comes after the main run
        assert p["flags"] == [{"type": "required_item_missing", "level": "info", "reason": "no README"}]
        assert p["originality"]["repo_found"] is True and p["originality"]["languages"] == {"Go": 100}
        assert any("not a verdict" in n for n in p["originality"]["notes"])
        b = r["projects"][1]
        assert b["status"] == "no_live_link" and b["talnex"]["score10"] is None and b["talnex"]["low_coverage"] is True
        assert b["originality"]["repo_found"] is False and b["originality"]["notes"]
        assert r["flags"][0]["type"] == "hidden_ai_instructions"
        assert r["coding_signals"] == [{"site": "leetcode", "signal": "leetcode_profile", "weight": "not_suspicious",
                                        "contest": None, "evidence": {"a": 1}}]
        assert any("could not be tested" in n and "not counted against" in n for n in r["notes"])
        assert "overall" not in json.dumps(r).lower().replace("overall score", "")  # no overall score field

    def test_never_holds_resume_text_or_storage_secrets(self, pool):
        cid, *_ = _seed(pool)
        text = json.dumps(build_report(pool, cid))
        assert SECRET_BULLET not in text and "resumes/x" not in text and "resume_key" not in text

    def test_time_saved_math(self, pool):
        cid, good, bare = _seed(pool)
        start = datetime.now(timezone.utc) - timedelta(minutes=5, seconds=10)
        with pool.connection() as conn:
            conn.execute("UPDATE jobs SET created_at = %s, updated_at = %s WHERE target_id = %s::uuid", (start, start, good))
            conn.execute("UPDATE jobs SET updated_at = now() WHERE target_id = %s::uuid", (bare,))
        t = build_report(pool, cid)["time_saved"]
        assert t["manual_minutes_estimate"] == 24            # two projects with a link or repo, 12 minutes each
        assert t["talnex_minutes"] == 6                       # 5 min 10 s rounds up
        assert t["saved_minutes"] == 18

    def test_saved_minutes_never_negative_and_no_projects(self, pool):
        cid = _candidate(pool)
        t = build_report(pool, cid)["time_saved"]
        assert t["manual_minutes_estimate"] == 0 and t["saved_minutes"] == 0 and t["talnex_minutes"] >= 1

    def test_has_gaps_cases(self, pool):
        full = _candidate(pool)
        p = _project(pool, full, "Full", "https://a.example.com")
        _claim(pool, p, "One", "works", 9)
        _claim(pool, p, "Code only", "reviewed_from_code", 5)
        assert build_report(pool, full)["has_gaps"] is False

        feature_gap = _candidate(pool)
        p = _project(pool, feature_gap, "Gap", "https://b.example.com")
        _claim(pool, p, "One", "works", 9)
        _claim(pool, p, "Two", "could_not_test")
        assert build_report(pool, feature_gap)["has_gaps"] is True

        no_link = _candidate(pool)
        p = _project(pool, no_link, "NoLink", None, "https://github.com/x/y")
        _claim(pool, p, "One", "reviewed_from_code", 5)
        assert build_report(pool, no_link)["has_gaps"] is True

        dead = _candidate(pool)
        p = _project(pool, dead, "Dead", "https://dead.example.com")
        _claim(pool, p, "One", "could_not_test")
        r = build_report(pool, dead)
        assert r["has_gaps"] is True and r["projects"][0]["status"] == "could_not_test"
        assert r["projects"][0]["status_reason"]

    def test_missing_candidate(self, pool):
        with pytest.raises(LookupError):
            build_report(pool, str(uuid.uuid4()))


def _stored(pool, cid):
    with pool.connection() as conn:
        return conn.execute("SELECT report, has_gaps FROM candidate_reports WHERE candidate_id = %s::uuid", (cid,)).fetchall()


class TestHandler:
    def test_saves_and_replaces_on_rerun(self, pool):
        cid, good, _ = _seed(pool)
        out = run(pool, "candidate_report", "candidate", cid, "recruiter_report")
        assert out["projects"] == 2 and out["has_gaps"] is True
        rows = _stored(pool, cid)
        assert len(rows) == 1 and rows[0][1] is True and rows[0][0]["version"] == 1
        with pool.connection() as conn:
            conn.execute("UPDATE claims SET testable = false, untestable_reason = 'x' WHERE text = 'Paid plans'")
            conn.execute("UPDATE candidate_projects SET live_url = 'https://c.example.com' WHERE name = 'ChatSummarizer'")
            conn.execute("UPDATE results SET verdict = 'works', feature_score = 8 WHERE claim_id IN (SELECT id FROM claims WHERE text = 'Export to PDF')")
        run(pool, "candidate_report", "candidate", cid, "recruiter_report")
        rows = _stored(pool, cid)
        assert len(rows) == 1                                   # replaced, not added
        names = {p["name"]: p["status"] for p in rows[0][0]["projects"]}
        assert names["ChatSummarizer"] == "could_not_test"      # has a link now, nothing tested

    def test_report_is_deleted_with_the_candidate(self, pool):
        cid, *_ = _seed(pool)
        run(pool, "candidate_report", "candidate", cid, "recruiter_report")
        with pool.connection() as conn:
            conn.execute("DELETE FROM candidates WHERE id = %s::uuid", (cid,))
        assert _stored(pool, cid) == []


class TestPipeline:
    def test_stage_order_is_data(self, pool):
        with pool.connection() as conn:
            rows = conn.execute("SELECT stage, runner, target_type, after_stages, time_limit_seconds FROM pipeline_stages "
                                "WHERE pipeline = 'recruiter_report' ORDER BY stage").fetchall()
        assert rows == [("candidate_report", "python", "candidate", [], 600),
                        ("resume_cleanup", "go", "candidate", ["candidate_report"], 300)]

    def test_last_project_starts_it_once(self, pool):
        cid = _candidate(pool)
        a = _project(pool, cid, "A", "https://a.example.com")
        b = _project(pool, cid, "B", "https://b.example.com")
        run(pool, "project_summary", "candidate_project", a, "recruiter")
        run(pool, "project_summary", "candidate_project", b, "recruiter")
        run(pool, "project_summary", "candidate_project", b, "recruiter")   # a repeat adds nothing
        with pool.connection() as conn:
            kinds = [r[0] for r in conn.execute("SELECT job_type FROM jobs WHERE target_id = %s::uuid", (cid,)).fetchall()]
        assert kinds == ["candidate_report"]
        # and the queue moves on to the Go cleanup stage once the report job is done
        with pool.connection() as conn:
            row = conn.execute("SELECT id::text FROM jobs WHERE target_id = %s::uuid", (cid,)).fetchone()
            conn.execute("UPDATE jobs SET status = 'running', locked_by = 'w' WHERE id = %s::uuid", (row[0],))
        queue.complete_job(pool, row[0], "w", {})
        with pool.connection() as conn:
            kinds = sorted(r[0] for r in conn.execute("SELECT job_type FROM jobs WHERE target_id = %s::uuid", (cid,)).fetchall())
        assert kinds == ["candidate_report", "resume_cleanup"]
