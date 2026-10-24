"""Try the copy check between teams on a handful of repositories, without the website.

    python -m talnex_ai.worker.copy_check --repo https://github.com/a/one --repo https://github.com/b/two --repo https://github.com/c/three --wait

It makes a throwaway organizer, an open-theme event, one team per repository (named Team 1, Team 2, ...), and starts the
`hackathon_event` pipeline directly (the stage that normally starts when the last team has its report). A Python worker and the
sandbox host must be running. With --wait it prints the pairs, their shared percentages and the flags.
"""
from __future__ import annotations

import argparse
import time
import uuid

from talnex_ai import settings as settings_module
from talnex_ai.db import open_pool
from talnex_ai.db.jobs import start_pipeline

DEV_EMAIL = "dev@talnex.local"


def create_event(pool, repos: list[str]) -> tuple[str, list[str]]:
    with pool.connection() as conn:
        owner = conn.execute(
            "INSERT INTO users (email) VALUES (%s) ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id::text", (DEV_EMAIL,)).fetchone()[0]
        event = conn.execute(
            "INSERT INTO events (owner_id, name, mode, role_level, starts_at, ends_at) VALUES (%s::uuid, %s, 'open_theme', 'fresher', now(), now() + interval '1 day') RETURNING id::text",
            (owner, f"Dev copy check {uuid.uuid4().hex[:6]}")).fetchone()[0]
        ids = [conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s::uuid, %s, %s) RETURNING id::text",
                            (event, f"Team {i}", url)).fetchone()[0] for i, url in enumerate(repos, start=1)]
    return event, ids


def print_report(pool, event_id: str) -> None:
    with pool.connection() as conn:
        job = conn.execute("SELECT status, result, error FROM jobs WHERE pipeline = 'hackathon_event' AND target_id = %s::uuid", (event_id,)).fetchone()
        pairs = conn.execute(
            """SELECT a.team_name, b.team_name, c.shared_pct, c.level, c.matching_files FROM copy_pairs c
                 JOIN projects a ON a.id = c.project_a_id JOIN projects b ON b.id = c.project_b_id
                WHERE c.event_id = %s::uuid ORDER BY c.shared_pct DESC""", (event_id,)).fetchall()
        flags = conn.execute(
            """SELECT p.team_name, f.level, f.reason, f.evidence->>'verdict', f.evidence->>'ai_reason' FROM flags f JOIN projects p ON p.id = f.project_id
                WHERE p.event_id = %s::uuid AND f.flag_type = 'copied_from_team' ORDER BY p.team_name""", (event_id,)).fetchall()
    print(f"\nstage: {job[0]}" + (f" ({job[2]})" if job[2] else ""))
    if job[1]:
        print({k: v for k, v in job[1].items() if k != "top_pairs"})
    for a, b, pct, level, files in pairs:
        print(f"{a} <> {b}: {float(pct):g}% shared, flag: {level or 'none'}; top files: " + ", ".join(f"{m['a_file']}~{m['b_file']}" for m in files[:3]))
    for team, level, reason, verdict, ai in flags:
        print(f"flag on {team} [{level}] model: {verdict}: {ai}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Try the copy check between teams.")
    parser.add_argument("--repo", action="append", required=True, help="a public GitHub repository (give at least two)")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args(argv)
    if len(args.repo) < 2:
        parser.error("give at least two --repo")
    pool = open_pool(settings_module.load().database_url)
    event_id, _ = create_event(pool, args.repo)
    start_pipeline(pool, "hackathon_event", "event", event_id)
    print(f"started the event checks for event {event_id}")
    if args.wait:
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            with pool.connection() as conn:
                status = conn.execute("SELECT status FROM jobs WHERE pipeline = 'hackathon_event' AND target_id = %s::uuid", (event_id,)).fetchone()[0]
            if status in ("done", "failed"):
                break
            time.sleep(5)
        print_report(pool, event_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
