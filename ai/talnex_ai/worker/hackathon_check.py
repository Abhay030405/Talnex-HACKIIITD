"""Try the whole hackathon pipeline on one project, without the website.

    python -m talnex_ai.worker.hackathon_check --url https://demo.example.com \\
        --criterion "Add and complete todos:Add an item and tick it off:3" \\
        --criterion "Filter the list:Show only active or only completed items:1" --wait

It makes a throwaway organizer, a fixed-problem event with your criteria (or an open-theme one with
--open-theme and --repo) and one project with your links, then starts the `hackathon` pipeline. A
Python worker (and the Go worker, for the GitHub stages) must be running. With --wait it follows the
stages and prints each claim's verdict and score, the group scores, the weighted criteria total, the
flags and what the run cost. A criterion is `name:description:weight`.
"""
from __future__ import annotations

import argparse
import time
import uuid

from talnex_ai import settings as settings_module
from talnex_ai.db import open_pool
from talnex_ai.db.jobs import start_pipeline

DEV_EMAIL = "dev@talnex.local"


def parse_criterion(text: str) -> tuple[str, str, float]:
    parts = text.split(":")
    if len(parts) != 3:
        raise SystemExit(f"a criterion is name:description:weight, got {text!r}")
    name, description, weight = parts[0].strip(), parts[1].strip(), float(parts[2])
    if not name or weight <= 0:
        raise SystemExit(f"a criterion needs a name and a weight above 0, got {text!r}")
    return name, description, weight


def create_project(pool, *, url: str, name: str, role: str, criteria: list[tuple[str, str, float]], repo: str = "",
                   sponsors: tuple[str, ...] = (), starts_at: str = "", mode: str = "fixed_problem") -> str:
    with pool.connection() as conn:
        owner = conn.execute("""INSERT INTO users (email) VALUES (%s)
                                ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id::text""",
                             (DEV_EMAIL,)).fetchone()[0]
        event = conn.execute(
            """INSERT INTO events (owner_id, name, mode, role_level, starts_at, ends_at, sponsor_tools)
               VALUES (%s::uuid, %s, %s, %s, COALESCE(NULLIF(%s, '')::timestamptz, now()),
                       COALESCE(NULLIF(%s, '')::timestamptz, now()) + interval '1 day', %s) RETURNING id::text""",
            (owner, f"Dev hackathon {uuid.uuid4().hex[:6]}", mode, role, starts_at, starts_at, list(sponsors))).fetchone()[0]
        for cname, description, weight in criteria:
            conn.execute("INSERT INTO criteria (event_id, name, description, weight) VALUES (%s::uuid, %s, NULLIF(%s, ''), %s)",
                         (event, cname, description, weight))
        return conn.execute(
            """INSERT INTO projects (event_id, team_name, live_url, repo_url)
               VALUES (%s::uuid, %s, NULLIF(%s, ''), NULLIF(%s, '')) RETURNING id::text""",
            (event, name, url, repo)).fetchone()[0]


def print_report(pool, project_id: str) -> None:
    with pool.connection() as conn:
        claims = conn.execute(
            """SELECT c.claim_group, c.text, r.verdict, r.confidence, r.feature_score, r.score_reason
                 FROM claims c LEFT JOIN results r ON r.claim_id = c.id
                WHERE c.project_id = %s::uuid ORDER BY c.claim_group, c.importance DESC""", (project_id,)).fetchall()
        scores = conn.execute("""SELECT score_group, score, coverage, confidence FROM scores
                                  WHERE project_id = %s::uuid ORDER BY score_group""", (project_id,)).fetchall()
        status = conn.execute("SELECT status FROM projects WHERE id = %s::uuid", (project_id,)).fetchone()[0]
        flags = conn.execute("SELECT flag_type, level, reason FROM flags WHERE project_id = %s::uuid ORDER BY flag_type, reason",
                             (project_id,)).fetchall()
        skipped = conn.execute("""SELECT job_type, result->>'reason' FROM jobs
                                   WHERE target_id = %s::uuid AND result->>'skipped' = 'true'""", (project_id,)).fetchall()
        cost = conn.execute("""SELECT coalesce(sum(u.cost_usd), 0) FROM usage_log u JOIN jobs j ON j.id = u.job_id
                                WHERE j.target_id = %s::uuid""", (project_id,)).fetchone()[0]
    print()
    for group, text, verdict, confidence, score, reason in claims:
        shown = "no result" if verdict is None else f"{verdict.upper()} ({confidence})"
        print(f"[{group}] {text}\n    {shown}" + (f" | {float(score):g}/10" if score is not None else ""))
        if reason:
            print(f"    {reason}")
    print()
    for group, score, coverage, confidence in scores:
        shown = "not scored" if score is None else f"{float(score):g}/100"
        label = "weighted total (based on your criteria and tested claims only)" if group == "weighted_total" else group
        print(f"score {label}: {shown}, coverage {float(coverage):g}%" + (f", confidence {confidence}" if group != "weighted_total" else ""))
    for flag_type, level, reason in flags:
        print(f"flag {flag_type} [{level}] {reason}")
    for stage_name, reason in skipped:
        print(f"skipped {stage_name}: {reason}")
    print(f"\nProject status: {status}\nCost of this check: ${float(cost):.4f}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="", help="the live link to test (leave it out for a backend-only project)")
    parser.add_argument("--criterion", action="append", default=[], help="name:description:weight (repeat; needed unless --open-theme)")
    parser.add_argument("--open-theme", action="store_true", help="an open-theme event: claims come from the code (needs --repo)")
    parser.add_argument("--repo", default="", help="the GitHub repository link (turns on the repository checks)")
    parser.add_argument("--sponsor", action="append", default=[], help="a sponsor tool of the event (repeat for several)")
    parser.add_argument("--starts-at", default="", help="when the event started, e.g. 2026-10-20T09:00:00Z (default: now)")
    parser.add_argument("--role", choices=("fresher", "junior", "mid", "senior"), default="fresher")
    parser.add_argument("--name", default="Dev hackathon team")
    parser.add_argument("--wait", action="store_true", help="follow the stages and print the results")
    parser.add_argument("--timeout", type=int, default=1500, help="seconds to wait with --wait")
    args = parser.parse_args(argv)
    if args.open_theme and (args.criterion or not args.repo):
        parser.error("--open-theme takes a --repo and no --criterion")
    if not args.open_theme and not args.criterion:
        parser.error("give at least one --criterion (or use --open-theme)")

    pool = open_pool(settings_module.load().database_url)
    project_id = create_project(pool, url=args.url, name=args.name, role=args.role,
                                mode="open_theme" if args.open_theme else "fixed_problem",
                                criteria=[parse_criterion(c) for c in args.criterion], repo=args.repo,
                                sponsors=tuple(args.sponsor), starts_at=args.starts_at)
    start_pipeline(pool, "hackathon", "project", project_id)
    print(f"started the hackathon pipeline for project {project_id}")
    if not args.wait:
        return 0

    deadline, last = time.monotonic() + args.timeout, {}
    while time.monotonic() < deadline:
        with pool.connection() as conn:
            states = dict(conn.execute("SELECT job_type, status FROM jobs WHERE target_id = %s::uuid", (project_id,)).fetchall())
        if states != last:
            print("  stages:", ", ".join(f"{s}={state}" for s, state in states.items()))
            last = states
        if states.get("project_report") in ("done", "failed") or "failed" in states.values():
            break
        time.sleep(2)
    else:
        print("timed out; the pipeline may still be running")
    print_report(pool, project_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
