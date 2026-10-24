"""Stage `copy_between_teams` (event level): compare every pair of teams' code by shape and flag pairs that match too closely.

Runs once every team of the event is done (see `project_report`). Each team's repo is cloned into its own throwaway VM and
fingerprinted there; starter code that many teams share is removed; each pair gets a shared percentage. A pair at the review line
or above gets a last look from a model at its top matching files, which can only make the flag LESS serious (a template or a
standard pattern), never more. A team whose code could not be read is left out and listed, never marked. Flags sit beside the score.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Optional

from talnex_ai.checks.copy_between_teams import PairLook, fingerprint_repo, look_at_pair, lower, read_pair_files
from talnex_ai.checks.copy_between_teams.compare import Pair, Team, compare, level_for
from talnex_ai.db.jobs import Job
from talnex_ai.sandbox.client import SandboxError
from talnex_ai.sandbox.stack_detect.gather import RepoUnreachable
from talnex_ai.sandbox.stack_detect.recipe import FULL_IMAGE
from talnex_ai.scoring.flags.store import add_flag
from talnex_ai.worker.handlers.project_report import save_card
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall
from talnex_ai.worker.services import Services, get_services

log = logging.getLogger("talnex.copy_between_teams")

FLAG_TYPE = "copied_from_team"
FINGERPRINT_THREADS = 3


def _fingerprint_one(sv: Services, project: Mapping[str, str]) -> tuple[str, Any]:
    vm = sv.sandbox.open_vm(FULL_IMAGE)
    try:
        return project["id"], fingerprint_repo(vm, project["repo_url"])
    except RepoUnreachable as exc:
        return project["id"], str(exc)
    except SandboxError as exc:
        return project["id"], f"the sandbox host failed: {exc}"
    finally:
        vm.destroy()


def _look(sv: Services, job: Job, a: Mapping[str, str], b: Mapping[str, str], pair: Pair) -> Optional[PairLook]:
    files = [(m["a_file"], m["b_file"]) for m in pair.matching_files[: sv.cfg.copy.look_max_files]]
    if not files:
        return None
    vm = sv.sandbox.open_vm(FULL_IMAGE)
    try:
        texts = read_pair_files(vm, a["repo_url"], b["repo_url"], files)
    except (RepoUnreachable, SandboxError) as exc:
        log.warning("could not read the matching files of %s and %s: %s", a["team_name"], b["team_name"], exc)
        return None
    finally:
        vm.destroy()
    matches = [(af, bf, at, bt, m["pct"]) for (af, bf), (at, bt), m in zip(files, texts, pair.matching_files)]
    return look_at_pair(sv.model, a["team_name"], b["team_name"], pair.shared_pct, matches, job_id=job.id)


@stage("copy_between_teams")
@never_stall
def copy_between_teams(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    sv = get_services(ctx.pool)
    cfg = sv.cfg.copy
    if job.target_type != "event":
        return {"skipped": True, "reason": "this check works on a whole event"}
    event_id = job.target_id
    with ctx.pool.connection() as conn:
        rows = conn.execute("SELECT id::text, team_name, repo_url FROM projects WHERE event_id = %s::uuid ORDER BY team_name, id",
                            (event_id,)).fetchall()
    everyone = {r[0]: {"id": r[0], "team_name": r[1], "repo_url": r[2]} for r in rows}
    projects = [p for p in everyone.values() if p["repo_url"]][: cfg.max_teams]
    if len(projects) < 2:
        return {"skipped": True, "reason": "fewer than two teams gave a repository, so there is nothing to compare"}
    if sv.sandbox is None or not sv.cfg.sandbox.enabled:
        return {"skipped": True, "reason": "the sandbox host is not set up, so the code could not be read"}

    with ThreadPoolExecutor(max_workers=FINGERPRINT_THREADS) as pool:
        got = dict(pool.map(lambda p: _fingerprint_one(sv, p), projects))
    ctx.check()
    could_not_read = {pid: why for pid, why in got.items() if isinstance(why, str)}
    teams = [Team(pid, everyone[pid]["team_name"], files) for pid, files in got.items() if not isinstance(files, str)]
    out = compare(teams, share=cfg.starter_share)

    # Earlier results of this check are replaced: a re-run must not leave a flag for a pair that no longer matches.
    with ctx.pool.connection() as conn, conn.transaction():
        conn.execute("DELETE FROM copy_pairs WHERE event_id = %s::uuid", (event_id,))
        conn.execute("DELETE FROM flags WHERE flag_type = %s AND project_id IN (SELECT id FROM projects WHERE event_id = %s::uuid)",
                     (FLAG_TYPE, event_id))
    flagged: set[str] = set()
    details = []
    for pair in sorted(out.pairs, key=lambda p: -p.shared_pct):
        level = level_for(pair.shared_pct, cfg.review_pct, cfg.strong_pct)
        a, b = everyone[pair.a_id], everyone[pair.b_id]
        look = None
        if level is not None:
            look = _look(sv, job, a, b, pair)
            if look and look.verdict in ("starter_or_library", "common_pattern"):
                level = lower(level)
        evidence = {"shared_pct": pair.shared_pct, "matching_files": pair.matching_files, "starter_code_removed": out.starter_removed,
                    "verdict": look.verdict if look else None, "ai_reason": look.reason if look else None,
                    "ai_evidence": look.evidence if look else []}
        with ctx.pool.connection() as conn:
            conn.execute(
                """INSERT INTO copy_pairs (event_id, project_a_id, project_b_id, shared_pct, level, matching_files)
                   VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s::jsonb)""",
                (event_id, pair.a_id, pair.b_id, pair.shared_pct, level, json.dumps(pair.matching_files)))
        if level is not None:
            for mine, other in ((a, b), (b, a)):
                add_flag(ctx.pool, "project", mine["id"], FLAG_TYPE, level,
                         f"The code of this team has the same shape as the code of {other['team_name']}: {pair.shared_pct:.0f}% of the smaller team's own code. "
                         "A person should look; TalNex cannot tell who wrote it first.",
                         {**evidence, "other_team": other["team_name"], "other_project_id": other["id"]})
                flagged.add(mine["id"])
        details.append({"a": a["team_name"], "b": b["team_name"], "shared_pct": pair.shared_pct, "level": level,
                        "verdict": look.verdict if look else None})
    for pid in flagged:     # the proof cards were built before this check ran
        save_card(ctx.pool, pid)
    return {"teams_compared": len(teams), "pairs": len(out.pairs), "flagged_teams": len(flagged), "starter_code_removed": out.starter_removed,
            "starter_threshold_teams": out.starter_threshold, "left_out_too_little_code": [everyone[i]["team_name"] for i in out.left_out],
            "could_not_read": {everyone[i]["team_name"]: why for i, why in could_not_read.items()}, "top_pairs": details[:10]}
