"""The recruiter proof report (version 1, docs/phase4/01_plan.md). Pure code: reads what was saved, no model calls.

The report has no overall score and no ranking. A feature that could not be tested is shown with its reason and never
counts against anyone. It never holds resume text: only claims (results), what was seen on the tested site, and facts.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.checks.authorship import report as authorship_report
from talnex_ai.reports.proof import features

REPORT_VERSION = 1
MANUAL_MINUTES_PER_PROJECT = 12   # checking one project by hand takes 10 to 15 minutes (architecture)
LOW_COVERAGE_PERCENT = 50.0
TALNEX_GROUP = "talnex"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _num(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _features(conn, project_id: str, candidate: Optional[str] = None) -> list[dict]:
    """The claims of one resume project, with proof. The same helper builds the hackathon proof card (reports/proof.py)."""
    feats = features(conn, "candidate_project", project_id)
    authorship_report.attach(conn, "candidate_project", project_id, feats, candidate=candidate)
    return feats


def _stage_result(conn, pipeline: str, job_type: str, project_id: str) -> dict:
    row = conn.execute(
        """SELECT result FROM jobs WHERE pipeline = %s AND job_type = %s AND target_type = 'candidate_project'
              AND target_id = %s::uuid AND status = 'done' ORDER BY updated_at DESC LIMIT 1""",
        (pipeline, job_type, project_id)).fetchone()
    return (row[0] if row and isinstance(row[0], dict) else None) or {}


def _originality(conn, repo_url: Optional[str], project_id: str) -> dict:
    notes: list[str] = []
    if not repo_url:
        return {"repo_found": False, "created_at": None, "pushed_at": None, "fork": False, "languages": {},
                "notes": ["No repository link was given, so the repository was not checked."]}
    facts = _stage_result(conn, "recruiter", "github_check", project_id)
    found = bool(facts.get("found"))
    if not found:
        notes.append("Not checked: " + str(facts.get("reason") or "the repository could not be read") + ".")
    elif facts.get("fork"):
        notes.append("This repository is a fork" + (f" of {facts['forked_from']}" if facts.get("forked_from") else "") + ".")
    orig = _stage_result(conn, "recruiter", "originality", project_id)
    repo_vs_live = orig.get("repo_vs_live") or {}
    for line in repo_vs_live.get("flags") or []:
        notes.append(str(line))
    if repo_vs_live.get("skipped"):
        notes.append("Repository compared with the live site: not checked (" + str(repo_vs_live.get("reason")) + ").")
    tut = orig.get("tutorial_copy") or {}
    if tut.get("skipped"):
        notes.append("Tutorial copy: not checked (" + str(tut.get("reason")) + ").")
    elif tut.get("match") and tut.get("match") != "none":
        notes.append("Possible match with a tutorial or boilerplate: a possible match, not a verdict.")
    return {"repo_found": found, "created_at": _iso(facts.get("created_at")), "pushed_at": _iso(facts.get("pushed_at")),
            "fork": bool(facts.get("fork")), "languages": facts.get("languages") or {}, "notes": notes}


def _project(conn, row, candidate: Optional[str] = None) -> dict:
    pid, name, live_url, repo_url = row
    features = _features(conn, pid, candidate)
    testable = [f for f in features if f["testable"]]
    scored = [f for f in testable if f["score10"] is not None]
    score = conn.execute("SELECT score, coverage FROM scores WHERE candidate_project_id = %s::uuid AND score_group = %s",
                         (pid, TALNEX_GROUP)).fetchone()
    score10 = round(float(score[0]) / 10, 1) if score and score[0] is not None else None
    coverage = float(score[1]) if score else 0.0

    tested_any = any(f["verdict"] not in (None, "could_not_test") for f in testable)
    if not live_url:
        status, reason = "no_live_link", "No live link was given for this project, so it could not be used and tested."
    elif not tested_any:
        status, reason = ("could_not_test",
                          "The live site could not be tested. This is not counted against the candidate.")
    else:
        status, reason = "tested", ""

    flags = [{"type": t, "level": lvl, "reason": why} for t, lvl, why in conn.execute(
        "SELECT flag_type, level, reason FROM flags WHERE candidate_project_id = %s::uuid ORDER BY created_at, id", (pid,))]
    return {
        "id": pid, "name": name, "live_url": live_url, "repo_url": repo_url,
        "status": status, "status_reason": reason,
        "talnex": {"score10": score10, "coverage": coverage, "features_scored": len(scored),
                   "features_total": len(testable), "low_coverage": coverage < LOW_COVERAGE_PERCENT},
        "features": features, "flags": flags, "originality": _originality(conn, repo_url, pid),
    }


def _minutes_taken(conn, candidate_id: str) -> int:
    """First job start to last job end of this candidate and its projects, rounded up to whole minutes (at least 1)."""
    first, last = conn.execute(
        """SELECT min(created_at), max(updated_at) FROM jobs
            WHERE (target_type = 'candidate' AND target_id = %(c)s::uuid)
               OR (target_type = 'candidate_project' AND target_id IN
                     (SELECT id FROM candidate_projects WHERE candidate_id = %(c)s::uuid))""",
        {"c": candidate_id}).fetchone()
    if first is None or last is None:
        return 1
    return max(1, math.ceil((last - first).total_seconds() / 60))


def build_report(pool: ConnectionPool, candidate_id: str) -> dict:
    with pool.connection() as conn:
        cand = conn.execute("SELECT role_level FROM candidates WHERE id = %s::uuid", (candidate_id,)).fetchone()
        if cand is None:
            raise LookupError(f"candidate {candidate_id} does not exist")
        rows = conn.execute("SELECT id::text, name, live_url, repo_url FROM candidate_projects "
                            "WHERE candidate_id = %s::uuid ORDER BY created_at, id", (candidate_id,)).fetchall()
        projects = [_project(conn, r, authorship_report.candidate_account(pool, r[0])) for r in rows]
        signals = [{"site": site, "signal": signal, "weight": weight, "contest": contest, "evidence": evidence or {}}
                   for site, signal, weight, contest, evidence in conn.execute(
                       "SELECT site, signal, weight, contest, evidence FROM coding_signals "
                       "WHERE candidate_id = %s::uuid ORDER BY created_at, id", (candidate_id,))]
        flags = [{"type": t, "level": lvl, "reason": why} for t, lvl, why in conn.execute(
            "SELECT flag_type, level, reason FROM flags WHERE candidate_id = %s::uuid ORDER BY created_at, id", (candidate_id,))]
        talnex_minutes = _minutes_taken(conn, candidate_id)

    untested_features = sum(1 for p in projects for f in p["features"] if f["testable"] and f["verdict"] in (None, "could_not_test"))
    not_tested_projects = [p for p in projects if p["status"] != "tested"]
    has_gaps = bool(not_tested_projects or untested_features)

    notes: list[str] = []
    if untested_features:
        notes.append(f"{untested_features} feature{'s' if untested_features != 1 else ''} could not be tested; "
                     "they are not counted against the candidate.")
    for p in not_tested_projects:
        notes.append(f"{p['name']}: {p['status_reason']}")
    if signals:
        notes.append("Coding signals are hints to look at, not proof of cheating.")
    if not projects:
        notes.append("No projects were found on the resume.")

    manual = MANUAL_MINUTES_PER_PROJECT * sum(1 for p in projects if p["live_url"] or p["repo_url"])
    return {
        "version": REPORT_VERSION, "candidate_id": candidate_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role_level": cand[0], "has_gaps": has_gaps,
        "time_saved": {"manual_minutes_estimate": manual, "talnex_minutes": talnex_minutes,
                       "saved_minutes": max(0, manual - talnex_minutes)},
        "projects": projects, "coding_signals": signals, "flags": flags, "notes": notes,
    }
