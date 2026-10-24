"""Try the live-testing pipeline on its own, without a resume or a video.

    python -m talnex_ai.worker.live_check --url https://demo.example.com \\
        --claim "Add a todo item to the list" --claim "Delete a todo" --wait

It makes a throwaway owner and project (a project on a resume by default, or a hackathon project with
--project), saves your claims, and starts the `live_check` (or `live_check_project`) pipeline. A Python
worker must be running. With --wait it follows the stages and prints each claim's verdict, score and
reason, and what the check cost.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid

from talnex_ai import settings as settings_module
from talnex_ai.claims.store import Subject, save_claims
from talnex_ai.db import open_pool
from talnex_ai.db.jobs import start_pipeline
from talnex_ai.formats import Claim

DEV_EMAIL = "dev@talnex.local"
STAGES = ["precheck", "test_plan", "live_test", "proof_check", "feature_score"]


def create_subject(pool, *, project: bool, url: str, name: str, role: str) -> Subject:
    tag = f"Dev check {uuid.uuid4().hex[:6]}"
    with pool.connection() as conn:
        owner = conn.execute(
            """INSERT INTO users (email) VALUES (%s)
               ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id::text""", (DEV_EMAIL,)).fetchone()[0]
        if project:
            event = conn.execute(
                """INSERT INTO events (owner_id, name, mode, role_level, starts_at, ends_at)
                   VALUES (%s::uuid, %s, 'open_theme', %s, now(), now() + interval '1 day') RETURNING id::text""",
                (owner, tag, role)).fetchone()[0]
            row = conn.execute("INSERT INTO projects (event_id, team_name, live_url) VALUES (%s::uuid, %s, %s) RETURNING id::text",
                               (event, name, url)).fetchone()
            return Subject("project", row[0])
        candidate = conn.execute(
            "INSERT INTO candidates (owner_id, label, role_level) VALUES (%s::uuid, %s, %s) RETURNING id::text",
            (owner, tag, role)).fetchone()[0]
        row = conn.execute(
            "INSERT INTO candidate_projects (candidate_id, name, live_url) VALUES (%s::uuid, %s, %s) RETURNING id::text",
            (candidate, name, url)).fetchone()
        return Subject("candidate_project", row[0])


def stage_states(pool, subject: Subject) -> dict[str, str]:
    with pool.connection() as conn:
        return dict(conn.execute("SELECT job_type, status FROM jobs WHERE target_id = %s::uuid", (subject.id,)).fetchall())


def print_report(pool, subject: Subject) -> None:
    column = subject.column
    with pool.connection() as conn:
        rows = conn.execute(
            f"""SELECT c.text, r.verdict, r.confidence, r.feature_score, r.score_reason
                  FROM claims c LEFT JOIN results r ON r.claim_id = c.id
                 WHERE c.{column} = %s::uuid ORDER BY c.importance DESC, c.created_at""", (subject.id,)).fetchall()
        talnex = conn.execute(f"SELECT score, coverage FROM scores WHERE {column} = %s::uuid AND score_group = 'talnex'",
                              (subject.id,)).fetchone()
        flags = conn.execute(f"SELECT level, reason FROM flags WHERE {column} = %s::uuid", (subject.id,)).fetchall()
        cost = conn.execute("""SELECT coalesce(sum(u.cost_usd), 0) FROM usage_log u JOIN jobs j ON j.id = u.job_id
                                WHERE j.target_id = %s::uuid""", (subject.id,)).fetchone()[0]
    print()
    for text, verdict, confidence, score, reason in rows:
        shown = "no result" if verdict is None else f"{verdict.upper()} ({confidence})"
        print(f"- {text}\n    {shown}" + (f" | {float(score):g}/10" if score is not None else ""))
        if reason:
            print(f"    {reason}")
    for level, reason in flags:
        print(f"  flag [{level}] {reason}")
    if talnex:
        print(f"\nTalNex score: {float(talnex[0]) / 10:g}/10 (coverage {float(talnex[1]):g}%)")
    print(f"Cost of this check: ${float(cost):.4f}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="the live link to test")
    parser.add_argument("--claim", action="append", required=True, help="a claim to test (repeat for several)")
    parser.add_argument("--importance", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--role", choices=("fresher", "junior", "mid", "senior"), default="fresher")
    parser.add_argument("--name", default="Dev check project")
    parser.add_argument("--project", action="store_true", help="make a hackathon project instead of a resume project")
    parser.add_argument("--wait", action="store_true", help="follow the stages and print the results")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait with --wait")
    args = parser.parse_args(argv)

    pool = open_pool(settings_module.load().database_url)
    subject = create_subject(pool, project=args.project, url=args.url, name=args.name, role=args.role)
    save_claims(pool, subject, [Claim(text=t, claim_group="Core", importance=args.importance, source="readme")
                                for t in args.claim])
    pipeline = "live_check_project" if args.project else "live_check"
    start_pipeline(pool, pipeline, subject.kind, subject.id)
    print(f"started {pipeline} for {subject.kind} {subject.id}")
    if not args.wait:
        return 0

    deadline, last = time.monotonic() + args.timeout, {}
    while time.monotonic() < deadline:
        states = stage_states(pool, subject)
        if states != last:
            print("  stages:", ", ".join(f"{s}={states.get(s, '-')}" for s in STAGES))
            last = states
        if states.get("feature_score") in ("done", "failed") or "failed" in states.values():
            break
        time.sleep(2)
    else:
        print("timed out waiting for the stages to finish")
        return 2
    print_report(pool, subject)
    return 1 if "failed" in stage_states(pool, subject).values() else 0


if __name__ == "__main__":
    sys.exit(main())
