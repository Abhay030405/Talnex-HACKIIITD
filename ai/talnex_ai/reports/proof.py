"""The parts of a proof report that are the same for a hackathon project and for a project on a resume: the claims (features) of
one project, each with its verdict, score, reason and proof, and what was found when its code was read.

Shared by `recruiter_report.py` and `project_card.py`, so a feature looks the same on both and the sandbox track (backend
requests and answers, the repository's own tests, code review) shows up in both without either report knowing about it.
"""
from __future__ import annotations

from typing import Any, Optional

COLUMN = {"project": "project_id", "candidate_project": "candidate_project_id"}


def _num(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def proof_steps(conn, claim_id: str) -> list[dict]:
    """Steps of the main run, then the extra checks, numbered 1..n. The main run is the latest normal or access run; a claim TalNex
    made from the routes (edge cases, a route check, load, the repository's own tests) has no such run, so its latest run is the main one.
    A step's `proof_key` is a screenshot (live) or a saved request and answer (backend); the API turns it into a short-lived link."""
    runs = conn.execute(
        """SELECT id::text, (test_type IN ('normal', 'access')) AS is_main, test_type, track FROM test_runs
            WHERE claim_id = %s::uuid ORDER BY started_at DESC NULLS LAST""", (claim_id,)).fetchall()
    main = next((r for r in runs if r[1]), runs[0] if runs else None)
    ordered = ([main] if main else []) + [r for r in runs if main is None or r[0] != main[0]]
    out: list[dict] = []
    for run_id, _is_main, test_type, track in ordered:
        for action, observed, key, kind, devtools in conn.execute(
                "SELECT action, observed, proof_key, kind, devtools FROM steps WHERE run_id = %s::uuid ORDER BY step_number",
                (run_id,)):
            out.append({"step": len(out) + 1, "action": action, "observed": observed, "proof_key": key, "kind": kind,
                        "test_type": test_type, "track": track, "devtools": devtools})
    return out


def observations(steps: list[dict]) -> list[str]:
    """Short lines on what the browser's developer tools saw across a feature's steps (API errors, failed requests,
    console errors, slow calls): background evidence for a verdict, shown beside the proof, never a verdict itself."""
    notes: list[str] = []
    for step in steps:
        dt = step.get("devtools")
        if not isinstance(dt, dict):
            continue
        for c in dt.get("error_responses", []):
            ms = f", {c['ms']}ms" if c.get("ms") else ""
            notes.append(f"{c.get('method', 'GET')} {c.get('url', '')} answered {c.get('status')}{ms}")
        for f in dt.get("failed_requests", []):
            notes.append(f"request to {f.get('url', '')} failed")
        for e in dt.get("console_errors", []):
            notes.append(f"console: {e}")
        for e in dt.get("page_errors", []):
            notes.append(f"page error: {e}")
        for c in dt.get("api_calls", []):
            if c.get("ms", 0) >= 2000:
                notes.append(f"slow: {c.get('method', 'GET')} {c.get('url', '')} took {c['ms']}ms")
    seen: dict[str, None] = {}
    for n in notes:
        seen.setdefault(n, None)
    return list(seen)[:12]


def code_review_of(conn, claim_id: str) -> Optional[dict]:
    """What the code review found for a claim, trimmed for display, or None. Always labelled as read from the code, not run."""
    row = conn.execute(
        """SELECT sr.resources->'code_review'->%s::text
             FROM claims c
             JOIN sandbox_runs sr ON (c.project_id IS NOT NULL AND sr.project_id = c.project_id)
                                  OR (c.candidate_project_id IS NOT NULL AND sr.candidate_project_id = c.candidate_project_id)
            WHERE c.id = %s::uuid AND jsonb_exists(sr.resources->'code_review', %s::text)
            ORDER BY sr.created_at DESC LIMIT 1""", (claim_id, claim_id, claim_id)).fetchone()
    finding = row[0] if row else None
    if not finding:
        return None
    return {
        "label": "reviewed from code, not run",
        "mechanism": finding.get("mechanism"), "summary": finding.get("summary"),
        "evidence": (finding.get("evidence") or [])[:6], "quality": (finding.get("quality") or [])[:6],
        "ai": finding.get("ai") or {}, "files_read": (finding.get("files_read") or [])[:12],
    }


def features(conn, kind: str, subject_id: str) -> list[dict]:
    """Every claim of one project (kind is "project" or "candidate_project") with its result, score and proof."""
    column = COLUMN[kind]
    rows = conn.execute(
        f"""SELECT c.id::text, c.text, c.claim_group, c.importance, c.testable, c.untestable_reason, c.track, c.source,
                   r.verdict, r.confidence, r.reason, r.feature_score, r.score_reason
              FROM claims c LEFT JOIN results r ON r.claim_id = c.id
             WHERE c.{column} = %s::uuid ORDER BY c.importance DESC, c.created_at, c.id""", (subject_id,)).fetchall()
    lists = checklists(conn, kind, subject_id)
    out = []
    for cid, text, group, importance, testable, untestable, track, source, verdict, confidence, reason, score, score_reason in rows:
        steps = proof_steps(conn, cid) if verdict else []
        out.append({
            "claim_id": cid, "text": text, "group": group, "importance": importance,
            "testable": testable, "untestable_reason": untestable, "track": track, "source": source,
            "verdict": verdict, "confidence": confidence, "reason": reason,
            "score10": _num(score), "score_reason": score_reason,
            "proof": steps, "observations": observations(steps),
            "code_review": code_review_of(conn, cid),
            "checklist": lists.get(cid, []),
        })
    return out


def checklists(conn, kind: str, subject_id: str) -> dict[str, list[str]]:
    """What TalNex planned to check per claim, written before testing (test_plan for live claims, sandbox_plan for
    backend ones). Later runs win over earlier ones."""
    out: dict[str, list[str]] = {}
    for stage, result in conn.execute(
            """SELECT job_type, result FROM jobs WHERE target_type = %s AND target_id = %s::uuid
                AND job_type IN ('test_plan', 'sandbox_plan') AND status = 'done' ORDER BY run_number, updated_at""",
            (kind, subject_id)).fetchall():
        per_claim = (result or {}).get("claims" if stage == "test_plan" else "checklists") or {}
        for cid, entry in per_claim.items():
            items = ((entry or {}).get("checklist") or {}).get("items") or []
            texts = [str(i.get("text")) for i in items if isinstance(i, dict) and i.get("text")]
            if texts:
                out[cid] = texts
    return out


AREA_LABELS = {"production": "Production practices", "structure": "Project structure", "hygiene": "Repository hygiene",
               "commits": "Commit style", "docs": "Docs and setup", "consistency": "Consistency and error handling"}


def engineering(conn, kind: str, subject_id: str, repo_url: Optional[str]) -> Optional[dict]:
    """The repo_quality rows of one project, with a GitHub link on each piece of evidence, or None when not judged."""
    column = "project_id" if kind == "project" else "candidate_project_id"
    rows = conn.execute(f"SELECT area, score, summary, evidence FROM repo_quality WHERE {column} = %s::uuid "
                        "ORDER BY created_at, area", (subject_id,)).fetchall()
    if not rows:
        return None
    base = (repo_url or "").rstrip("/").removesuffix(".git")
    areas = []
    for area, score, summary, evidence in rows:
        items = []
        for e in evidence or []:
            if e.get("kind") == "commit" and base:
                e = {**e, "url": f"{base}/commit/{e.get('sha')}"}
            elif e.get("kind") == "file" and base:
                e = {**e, "url": f"{base}/{'tree' if str(e.get('path', '')).endswith('/') else 'blob'}/HEAD/{e.get('path')}"}
            items.append(e)
        areas.append({"area": area, "label": AREA_LABELS.get(area, area), "score": _num(score), "summary": summary,
                      "evidence": items})
    scored = [a["score"] for a in areas if a["score"] is not None]
    return {"areas": areas, "overall": round(sum(scored) / len(scored), 1) if scored else None}
