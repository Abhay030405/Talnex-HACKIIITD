"""What the VM (sandbox) track found for one project, for the report's "VM test" tab. Shared by the recruiter report
and the hackathon proof card. Plain reads of sandbox_runs and the sandbox stages' saved results; never a verdict on
its own: "could not run" is left out of every score.
"""
from __future__ import annotations

from typing import Any, Optional

STAGES = ("sandbox_run", "route_discovery", "sandbox_test", "repo_tests", "code_review")


def _plain(result: Any) -> dict:
    """A stage result without long lists: scalars, and small dicts of scalars (counts such as mechanisms)."""
    if not isinstance(result, dict):
        return {}
    out: dict = {}
    for k, v in result.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict) and all(isinstance(x, (str, int, float, bool)) for x in v.values()):
            out[k] = v
        elif isinstance(v, list):
            out[k + "_count"] = len(v)
    return out


def sandbox_facts(conn, column: str, subject_id: str, pipeline: str, live_url: Optional[str]) -> dict:
    """`column` is project_id or candidate_project_id; `pipeline` is hackathon or recruiter."""
    row = conn.execute(f"""SELECT status, status_detail, recipe, resources, build_log_key, run_log_key FROM sandbox_runs
                            WHERE {column} = %s::uuid ORDER BY created_at DESC LIMIT 1""", (subject_id,)).fetchone()
    stages = {}
    for job_type, result in conn.execute(
            """SELECT DISTINCT ON (job_type) job_type, result FROM jobs
                WHERE pipeline = %s AND target_id = %s::uuid AND job_type = ANY(%s) AND status = 'done'
                ORDER BY job_type, run_number DESC, updated_at DESC""", (pipeline, subject_id, list(STAGES))):
        stages[job_type] = _plain(result)
    base = {"no_live_link": not live_url, "stages": stages}
    if row is None:
        reason = stages.get("sandbox_run", {}).get("reason") or "no repository was run in a VM"
        return {**base, "ran": False, "reason": reason}
    status, detail, recipe, resources, build_log, run_log = row
    recipe, resources = recipe or {}, resources or {}
    discovery = resources.get("discovery") or {}
    return {**base, "ran": status in ("running", "done"), "status": status, "detail": detail, "stack": recipe.get("stack"),
            "recipe_source": recipe.get("source"), "needed_a_fix": recipe.get("source") == "model_fix",
            "notes": recipe.get("notes") or [], "routes_found": len(discovery.get("routes") or []),
            "spec_found": bool(discovery.get("spec_found")), "build_log_key": build_log, "run_log_key": run_log}
