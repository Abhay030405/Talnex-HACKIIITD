"""The hackathon proof card for one project (version 1). Plain code: it reads what was saved and makes
no model calls.

Shown to the organizer who owns the event. It never ranks teams and never picks a winner. A feature
that couldn't be tested is shown with its reason and never counts against the team. Red flags sit
beside the score and are never subtracted. Features judged only by reading the code are labelled
"reviewed from code, not run" and capped at 7 out of 10 by the score stage.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from psycopg_pool import ConnectionPool

from talnex_ai.checks.authorship import report as authorship_report
from talnex_ai.checks.authorship.identity import identity_of
from talnex_ai.claims.store import Subject
from talnex_ai.reports.sandbox import sandbox_facts
from talnex_ai.reports.proof import engineering, features
from talnex_ai.reports.run_cost import run_usage

CARD_VERSION = 1
LOW_COVERAGE_PERCENT = 50.0
TALNEX_GROUP = "talnex"
WEIGHTED_GROUP = "weighted_total"
STANDARD_GROUPS = ("Access", "Core", "Logic", "Reliability")
SANDBOX_GROUPS = ("Setup", "Edge cases")
OPINION_LABEL = "AI opinion — not tested proof"
_KIND_ORDER = {"standard": 0, "backend": 1, "other": 2, "criterion": 3}


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else (None if value is None else str(value))


def _num(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _group_kind(name: str, criteria_names: set[str]) -> str:
    if name in criteria_names:
        return "criterion"
    if name in SANDBOX_GROUPS:
        return "backend"
    return "standard" if name in STANDARD_GROUPS else "other"


def _groups(conn, project_id: str, criteria: list[dict]) -> list[dict]:
    """Group scores: the organizer's criteria first, in their order; then the other groups by kind and
    name, never by score. A criterion nothing was claimed for still appears, unscored, so the organizer
    sees it wasn't covered."""
    names = {c["name"] for c in criteria}
    found = {}
    for group, score, coverage, confidence, used in conn.execute(
            "SELECT score_group, score, coverage, confidence, claims_used FROM scores WHERE project_id = %s::uuid",
            (project_id,)):
        if group in (TALNEX_GROUP, WEIGHTED_GROUP):
            continue
        cov = _num(coverage) or 0.0
        found[group] = {"group": group, "kind": _group_kind(group, names), "score": _num(score), "coverage": cov,
                        "confidence": confidence, "claims_used": used, "low_coverage": cov < LOW_COVERAGE_PERCENT}
    ordered = [found.get(c["name"]) or {"group": c["name"], "kind": "criterion", "score": None, "coverage": 0.0,
                                        "confidence": None, "claims_used": 0, "low_coverage": True} for c in criteria]
    rest = sorted((g for g in found.values() if g["group"] not in names), key=lambda g: (_KIND_ORDER[g["kind"]], g["group"]))
    return ordered + rest


def _checks(conn, project_id: str) -> list[dict]:
    """The stages of the latest run that didn't do their job: failed, skipped (with the reason), or not built.
    A stage that ran normally isn't listed."""
    run = conn.execute("SELECT max(run_number) FROM jobs WHERE target_id = %s::uuid AND pipeline = 'hackathon'",
                       (project_id,)).fetchone()[0]
    if run is None:
        return []
    out = []
    for job_type, status, result, error in conn.execute(
            """SELECT job_type, status, result, error FROM jobs
                WHERE target_id = %s::uuid AND pipeline = 'hackathon' AND run_number = %s ORDER BY created_at""",
            (project_id, run)):
        result = result if isinstance(result, dict) else {}
        if status == "failed":
            out.append({"stage": job_type, "status": "failed", "reason": (error or "the stage failed").splitlines()[0]})
        elif result.get("skipped"):
            out.append({"stage": job_type, "status": "skipped", "reason": str(result.get("reason") or "")})
        for part, value in result.items():  # a stage with several parts (originality): each part that was skipped
            if isinstance(value, dict) and value.get("skipped"):
                out.append({"stage": f"{job_type}: {part}", "status": "skipped", "reason": str(value.get("reason") or "")})
        for item in result.get("not_checked") or []:  # older results: a part that did not run, reason unknown
            out.append({"stage": job_type, "status": "skipped", "reason": f"{item}: not checked"})
    return out


def _opinion(conn, project_id: str, live: Optional[str]) -> Optional[dict]:
    """The AI opinion box, or None until the event-level opinion stage has run. Never part of any score."""
    rows = {kind: (parts, models) for kind, parts, models in conn.execute(
        "SELECT kind, parts, models FROM opinions WHERE project_id = %s::uuid", (project_id,))}
    if not rows:
        return None
    box: dict = {"label": OPINION_LABEL, "ui": None, "innovation": None, "models": []}
    for kind in ("ui", "innovation"):
        if kind in rows:
            parts, models = rows[kind]
            box[kind] = {"parts": parts,
                         "disagreement_note": "models disagree" if any(p.get("disagree") for p in parts) else None}
            box["models"] = list(models or [])
    if box["ui"] is None:
        box["ui_note"] = ("a repository-only project has no screens to judge, so there is no UI opinion" if not live
                          else "the live site could not be opened for screenshots, so there is no UI opinion")
    return box


def _notes(untested: int, from_code: int, live: Optional[str], repo: Optional[str]) -> list[str]:
    notes = ["Red flags are shown beside the score and are never subtracted from it.",
             "No team is ranked and no winner is picked: the people deciding make that call."]
    if untested:
        notes.append(f"{_plural(untested, 'feature')} could not be tested; they are left out of the scores and never "
                     "count against the team.")
    if from_code:
        notes.append(f"{_plural(from_code, 'feature')} {'was' if from_code == 1 else 'were'} judged by reading the code, "
                     "not by running it; those scores are capped at 7 out of 10.")
    if not live and repo:
        notes.append("This project has no live link, so it was judged from its repository: the backend was run in a "
                     "sandbox, not used through a website.")
    return notes


def build_project_card(pool: ConnectionPool, project_id: str) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT p.team_name, p.video_url, p.live_url, p.repo_url, p.status, e.id::text, e.name, e.mode, e.role_level,
                      e.starts_at, e.ends_at
                 FROM projects p JOIN events e ON e.id = p.event_id WHERE p.id = %s::uuid""", (project_id,)).fetchone()
        if row is None:
            raise LookupError(f"project {project_id} does not exist")
        team, video, live, repo, status, event_id, event_name, mode, role, starts, ends = row
        criteria = [{"name": n, "description": d or "", "weight": float(w)} for n, d, w in conn.execute(
            "SELECT name, description, weight FROM criteria WHERE event_id = %s::uuid ORDER BY weight DESC, name", (event_id,))]
        feats = features(conn, "project", project_id)
        engineering_card = engineering(conn, "project", project_id, repo)
        authorship_report.attach(conn, "project", project_id, feats)
        groups = _groups(conn, project_id, criteria)
        talnex_row = conn.execute("SELECT score, coverage, confidence FROM scores WHERE project_id = %s::uuid AND score_group = %s",
                                  (project_id, TALNEX_GROUP)).fetchone()
        weighted_row = conn.execute("SELECT score, coverage, claims_used FROM scores WHERE project_id = %s::uuid AND score_group = %s",
                                    (project_id, WEIGHTED_GROUP)).fetchone()
        flags = [{"type": t, "level": level, "reason": why, "evidence": ev or {}} for t, level, why, ev in conn.execute(
            "SELECT flag_type, level, reason, evidence FROM flags WHERE project_id = %s::uuid ORDER BY created_at, id",
            (project_id,))]
        checks = _checks(conn, project_id)
        sandbox = sandbox_facts(conn, "project_id", project_id, "hackathon", live)
        opinion = _opinion(conn, project_id, live)
        run = run_usage(conn, [("project", project_id)])

    testable = [f for f in feats if f["testable"]]
    scored = [f for f in testable if f["score10"] is not None]
    untested = [f for f in testable if f["verdict"] in (None, "could_not_test")]
    from_code = [f for f in testable if f["verdict"] == "reviewed_from_code"]
    coverage = (_num(talnex_row[1]) if talnex_row else None) or 0.0

    weighted = None
    if mode == "fixed_problem":
        weighted = {"score": _num(weighted_row[0]) if weighted_row else None,
                    "weight_covered": _num(weighted_row[1]) if weighted_row else 0.0,
                    "criteria_used": weighted_row[2] if weighted_row else 0, "criteria_total": len(criteria),
                    "label": "based on your criteria and tested claims only"}
    talnex_score = _num(talnex_row[0]) if talnex_row else None
    return {
        "version": CARD_VERSION, "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "team_name": team, "status": status, "links": {"video": video, "live": live, "repo": repo},
        "event": {"id": event_id, "name": event_name, "mode": mode, "role_level": role, "starts_at": _iso(starts),
                  "ends_at": _iso(ends)},
        "criteria": criteria,
        "talnex": {"score10": round(talnex_score / 10, 1) if talnex_score is not None else None, "coverage": coverage,
                   "confidence": talnex_row[2] if talnex_row else None, "features_scored": len(scored),
                   "features_total": len(testable), "low_coverage": coverage < LOW_COVERAGE_PERCENT},
        "weighted_total": weighted, "groups": groups, "features": feats, "flags": flags, "checks": checks,
        "sandbox": sandbox,
        "engineering": engineering_card,
        "who_built_what": authorship_report.who_built_what(
            feats, list(identity_of(pool, Subject("project", project_id)).accounts)),
        "ai_opinion": opinion,  # labelled "AI opinion — not tested proof"; None until the event-level opinion stage runs
        "run": run,  # how long this check took and what it cost (model and browser apart); None if it never ran
        "has_gaps": bool(untested or any(c["status"] == "failed" for c in checks)),
        "notes": _notes(len(untested), len(from_code), live, repo),
    }
