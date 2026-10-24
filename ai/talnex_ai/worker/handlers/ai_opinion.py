"""Stage `ai_opinion` (event level): the UI opinion and the innovation opinion of every team.

Always labelled "AI opinion — not tested proof" and never part of any score. Runs after the feature
comparison, once every team has its proof card.

- Innovation, for every team with features: compared with similar products from a web search and
  with the other teams of the event; difficulty is judged only from what was SEEN in testing.
- UI, only for a team with a live site (a repo-only project has no screens, by design): desktop and
  phone screenshots of its first page, plus a couple of screens from passed tests.

Two separate calls score each opinion and their scores are averaged (`scoring/ai_opinion`). Anything
that can't be done (the site not opening, both calls failing) leaves that opinion out, with the
reason in the stage result; it is never a mark against the team. A re-run replaces earlier opinions.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from talnex_ai.db.jobs import Job
from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.models import model_for
from talnex_ai.llm.prompts import opinion as prompts
from talnex_ai.llm.structured import ask_json
from talnex_ai.scoring.ai_opinion import INNOVATION_PARTS, LABEL, UI_PARTS, Judged, merge, read_answer
from talnex_ai.scoring.ai_opinion.capture import capture
from talnex_ai.worker.handlers.project_report import save_card
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.resilience import never_stall

log = logging.getLogger("talnex.ai_opinion")

TEST_SHOTS = 2       # screens from passed tests added to the two page shots, so "consistency" sees more than one page
MAX_FEATURES = 8
MAX_OTHER_TEAMS = 12
SEARCH_HITS = 5

_FEATURES = """
SELECT c.text, r.verdict FROM claims c LEFT JOIN results r ON r.claim_id = c.id
 WHERE c.project_id = %s::uuid ORDER BY c.importance DESC, c.created_at, c.id
"""
# One screen per passed claim (its last step), most important claims first.
_TEST_SHOTS = """
SELECT DISTINCT ON (c.importance, c.id) s.proof_key
  FROM steps s JOIN test_runs tr ON tr.id = s.run_id JOIN claims c ON c.id = tr.claim_id
 WHERE c.project_id = %s::uuid AND tr.track = 'live' AND tr.outcome = 'passed'
   AND s.kind = 'screen' AND s.proof_key IS NOT NULL
 ORDER BY c.importance DESC, c.id, s.step_number DESC
 LIMIT %s
"""


class _Described(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    description: str = ""
    search_query: str = ""


def seen_in_tests(features: Sequence[tuple[str, Optional[str]]]) -> str:
    """What testing actually showed, for judging difficulty. Claims nobody could test say nothing."""
    worked = [t for t, v in features if v == "works"]
    partly = [t for t, v in features if v == "partly_works"]
    from_code = [t for t, v in features if v == "reviewed_from_code"]
    lines = [f"Worked when tested: {len(worked)}. Partly worked: {len(partly)}. "
             f"Only reviewed from code, not run: {len(from_code)}."]
    lines += [f"- worked: {t}" for t in worked[:MAX_FEATURES]]
    lines += [f"- partly worked: {t}" for t in partly[:3]]
    lines += [f"- reviewed from code, not run: {t}" for t in from_code[:3]]
    return "\n".join(lines)


def _two_calls(model, system_a: str, system_b: str, user: str, allowed: list[str], images: Sequence[bytes],
               job_id: Optional[str]) -> tuple[Optional[dict[str, Judged]], Optional[dict[str, Judged]]]:
    """Both opinion calls at once. One failing is covered by the other; both failing gives (None, None)."""
    def one(role: str, system: str):
        try:
            return ask_json(model, role, system, user, lambda text: read_answer(text, allowed),
                            job_id=job_id, max_tokens=1500, images=images)
        except Exception as err:
            log.warning("the %s call failed: %s", role, err)
            return None

    with ThreadPoolExecutor(max_workers=2) as threads:
        a = threads.submit(one, "opinion_a", system_a)
        b = threads.submit(one, "opinion_b", system_b)
        return a.result(), b.result()


def _save(pool, project_id: str, kind: str, parts: list[dict], models: list[str]) -> None:
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO opinions (project_id, kind, parts, models) VALUES (%s::uuid, %s, %s::jsonb, %s)
               ON CONFLICT (project_id, kind) DO UPDATE SET parts = EXCLUDED.parts, models = EXCLUDED.models, created_at = now()""",
            (project_id, kind, json.dumps(parts), models))


def _drop(pool, project_id: str, kind: str) -> None:
    """An opinion that could not be made this run must not leave an older one behind on the card."""
    with pool.connection() as conn:
        conn.execute("DELETE FROM opinions WHERE project_id = %s::uuid AND kind = %s", (project_id, kind))


def _test_shots(pool, files, project_id: str) -> list[bytes]:
    with pool.connection() as conn:
        keys = [r[0] for r in conn.execute(_TEST_SHOTS, (project_id, TEST_SHOTS)).fetchall()]
    shots = []
    for key in keys:
        try:
            shots.append(files.get_bytes(key))
        except Exception as err:
            log.warning("could not read test screenshot %s: %s", key, err)
    return shots


def opinions_for_event(pool, sv, event_id: str, *, job_id: Optional[str] = None,
                       check: Callable[[], None] = lambda: None) -> dict[str, Any]:
    """Make and save both opinions for every team of an event. `sv` holds the shared clients:
    model, tinyfish, files, connect and cfg."""
    with pool.connection() as conn:
        teams = conn.execute("SELECT id::text, team_name, live_url FROM projects WHERE event_id = %s::uuid ORDER BY team_name, id",
                             (event_id,)).fetchall()
        features = {pid: conn.execute(_FEATURES, (pid,)).fetchall() for pid, _, _ in teams}
    models = [model_for(sv.cfg.llm, "opinion_a"), model_for(sv.cfg.llm, "opinion_b")]
    made: dict[str, list[str]] = {}
    not_made: dict[str, list[str]] = {}

    def note(team: str, why: str) -> None:
        not_made.setdefault(team, []).append(why)

    described: dict[str, _Described] = {}
    for pid, team, _ in teams:
        if not features[pid]:
            note(team, "no features were found, so there is no opinion")
            continue
        try:
            described[pid] = ask_json(sv.model, "claim_reader", prompts.DESCRIBE,
                                      prompts.describe_user(team, [t for t, _ in features[pid][:MAX_FEATURES]]),
                                      lambda text: parse_model(_Described, text), job_id=job_id, max_tokens=500)
        except Exception as err:
            log.warning("could not describe team %s: %s", team, err)
            note(team, "the project could not be described, so there is no opinion")
    check()

    for pid, team, live in teams:
        info = described.get(pid)
        if info is None or not info.description:
            _drop(pool, pid, "innovation")
            _drop(pool, pid, "ui")
            continue

        # ---- innovation
        hits = []
        if info.search_query:
            try:
                hits = sv.tinyfish.search(info.search_query)[:SEARCH_HITS]
            except Exception as err:  # search off or failing: judged without it, and the reason says so
                log.warning("search failed for team %s: %s", team, err)
        others = [d.description for other, d in described.items() if other != pid and d.description][:MAX_OTHER_TEAMS]
        allowed = list(INNOVATION_PARTS)
        a, b = _two_calls(sv.model, prompts.INNOVATION_A, prompts.INNOVATION_B,
                          prompts.innovation_user(info.description, [(h.title, h.url, h.snippet) for h in hits], others,
                                                  seen_in_tests(features[pid])),
                          allowed, [], job_id)
        if a is None and b is None:
            _drop(pool, pid, "innovation")
            note(team, "the innovation opinion could not be made (both model calls failed)")
        else:
            parts = merge(a or {}, b or {}, allowed)
            for part in parts:
                if part["part"] == "new_vs_existing":
                    part["links"] = [{"title": h.title, "url": h.url} for h in hits]
            _save(pool, pid, "innovation", parts, models)
            made.setdefault(team, []).append("innovation")
        check()

        # ---- UI (only with a live site)
        if not live:
            _drop(pool, pid, "ui")
            continue
        url = live if "://" in live else "https://" + live
        shots = capture(sv.tinyfish, sv.files, sv.connect, pid, url, job_id=job_id)
        images = []
        for name in ("desktop", "phone"):
            if shots.get(name):
                try:
                    images.append(sv.files.get_bytes(shots[name]))
                except Exception as err:
                    log.warning("could not read the %s shot of team %s: %s", name, team, err)
        if not images:
            _drop(pool, pid, "ui")
            note(team, "the live site could not be opened for screenshots, so there is no UI opinion")
            continue
        images += _test_shots(pool, sv.files, pid)
        allowed = list(UI_PARTS)
        a, b = _two_calls(sv.model, prompts.UI_A, prompts.UI_B, prompts.ui_user(team, len(images)), allowed, images, job_id)
        if a is None and b is None:
            _drop(pool, pid, "ui")
            note(team, "the UI opinion could not be made (both model calls failed)")
            continue
        keys = {name: shots.get("desktop") for name in allowed}
        keys["phone_width"] = shots.get("phone")
        _save(pool, pid, "ui", merge(a or {}, b or {}, allowed, keys), models)
        made.setdefault(team, []).append("ui")
        check()

    for pid, team, _ in teams:  # the proof cards were built before the opinions existed
        save_card(pool, pid)
    return {"label": LABEL, "opinions": made, "not_made": not_made, "models": models}


@stage("ai_opinion")
@never_stall
def ai_opinion(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    if job.target_type != "event":
        return {"skipped": True, "reason": "this check works on a whole event"}
    from talnex_ai.worker.services import get_services  # the shared clients; imported when the stage runs

    return opinions_for_event(ctx.pool, get_services(ctx.pool), job.target_id, job_id=job.id, check=ctx.check)
