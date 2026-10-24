"""Try the sandbox track on a real GitHub repo, without the website.

    python -m talnex_ai.worker.sandbox_check --repo https://github.com/heroku/node-js-getting-started [--candidate] [--keep]

It makes a throwaway project (or a project on a resume with --candidate) and starts the `sandbox_check_project` (or
`sandbox_check`) pipeline: sandbox_run (clone, build, start) > route_discovery > sandbox_plan > sandbox_test > sandbox_end.
It waits for the Python worker, then prints what happened: the recipe, the port, the stages, and each backend claim's verdict
with its reason. The VM is destroyed by the last stage. With --stop-after-run it stops after the first stage instead and
destroys the VM itself (unless --keep). The VM host (sandboxd) must be running, and so must a Python worker.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid

from talnex_ai import settings as settings_module
from talnex_ai.claims.store import Subject
from talnex_ai.db import open_pool
from talnex_ai.db.jobs import start_pipeline
from talnex_ai.sandbox.client import SandboxClient, SandboxError
from talnex_ai.sandbox.store import latest_run
from talnex_ai.storage import Store

DEV_EMAIL = "dev@talnex.local"


def create_subject(pool, *, repo: str, name: str, candidate: bool) -> Subject:
    with pool.connection() as conn:
        owner = conn.execute(
            "INSERT INTO users (email) VALUES (%s) ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id::text",
            (DEV_EMAIL,)).fetchone()[0]
        if candidate:
            cid = conn.execute("INSERT INTO candidates (owner_id, label) VALUES (%s::uuid, %s) RETURNING id::text",
                               (owner, f"Sandbox check {uuid.uuid4().hex[:6]}")).fetchone()[0]
            sid = conn.execute("INSERT INTO candidate_projects (candidate_id, name, repo_url) VALUES (%s::uuid, %s, %s) RETURNING id::text",
                               (cid, name, repo)).fetchone()[0]
            return Subject("candidate_project", sid)
        eid = conn.execute(
            """INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
               VALUES (%s::uuid, %s, 'open_theme', now(), now() + interval '1 day') RETURNING id::text""",
            (owner, f"Sandbox check {uuid.uuid4().hex[:6]}")).fetchone()[0]
        sid = conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s::uuid, %s, %s) RETURNING id::text",
                           (eid, name, repo)).fetchone()[0]
        return Subject("project", sid)


def _print_results(pool, subject: Subject) -> None:
    column = "project_id" if subject.kind == "project" else "candidate_project_id"
    with pool.connection() as conn:
        rows = conn.execute(
            f"""SELECT c.claim_group, c.text, r.verdict, r.confidence, r.reason
                  FROM claims c LEFT JOIN results r ON r.claim_id = c.id
                 WHERE c.{column} = %s::uuid AND c.track <> 'live' ORDER BY c.claim_group, c.importance DESC, c.text""",
            (subject.id,)).fetchall()
        runs = conn.execute(
            f"""SELECT count(*), count(*) FILTER (WHERE outcome = 'passed'), count(*) FILTER (WHERE outcome = 'failed'),
                       count(*) FILTER (WHERE outcome = 'blocked')
                  FROM test_runs t JOIN claims c ON c.id = t.claim_id
                 WHERE c.{column} = %s::uuid AND t.track = 'sandbox'""", (subject.id,)).fetchone()
    print(f"\n--- backend claims ({len(rows)}); HTTP runs: {runs[0]} (passed {runs[1]}, failed {runs[2]}, blocked {runs[3]}) ---")
    for group, text, verdict, confidence, reason in rows:
        shown = "no result" if verdict is None else f"{verdict.upper()} ({confidence})"
        print(f"[{group}] {text}\n    {shown} - {(reason or '')[:230]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="a public GitHub repository link")
    parser.add_argument("--name", default="Sandbox check project")
    parser.add_argument("--candidate", action="store_true", help="make a project on a resume instead of a hackathon project")
    parser.add_argument("--keep", action="store_true", help="with --stop-after-run, leave the VM running (it still ends at its time limit)")
    parser.add_argument("--stop-after-run", action="store_true", help="only wait for the first stage (clone, build, start)")
    parser.add_argument("--timeout", type=int, default=1500)
    args = parser.parse_args(argv)

    cfg = settings_module.load()
    pool = open_pool(cfg.database_url)
    subject = create_subject(pool, repo=args.repo, name=args.name, candidate=args.candidate)
    pipeline = "sandbox_check" if args.candidate else "sandbox_check_project"
    start_pipeline(pool, pipeline, subject.kind, subject.id)
    print(f"started {pipeline} for {subject.kind} {subject.id}")

    deadline = time.monotonic() + args.timeout
    final = "sandbox_run" if args.stop_after_run else "sandbox_end"
    last: dict = {}
    while time.monotonic() < deadline:
        with pool.connection() as conn:
            states = dict(conn.execute("SELECT job_type, status FROM jobs WHERE target_id = %s::uuid", (subject.id,)).fetchall())
        if states != last:
            print("  stages:", ", ".join(f"{k}={v}" for k, v in states.items()))
            last = states
        if states.get(final) in ("done", "failed") or "failed" in states.values():
            break
        time.sleep(3)
    else:
        print("timed out; the pipeline may still be running")
        return 1

    with pool.connection() as conn:
        jobs = conn.execute("SELECT job_type, status, result, error FROM jobs WHERE target_id = %s::uuid ORDER BY created_at",
                            (subject.id,)).fetchall()
    for job_type, status, result, error in jobs:
        brief = {k: v for k, v in (result or {}).items() if not isinstance(v, (dict, list))}
        print(f"\nstage {job_type}: {status}" + (f" ({error})" if error else "") + (f"  {json.dumps(brief)}" if brief else ""))
    run = latest_run(pool, subject)
    if run:
        print(f"\nsandbox run: {run.status}" + (f" - {run.status_detail}" if run.status_detail else ""))
        r = run.recipe or {}
        if r:
            print(f"recipe ({r.get('source')}, {r.get('confidence')} confidence): stack={r.get('stack')} dir={r.get('app_dir') or '.'}")
            print(f"  install: {r.get('install_cmd')}\n  build:   {r.get('build_cmd')}\n  start:   {r.get('start_cmd')}")
            for note in r.get("notes") or []:
                print(f"  note: {note}")
        store = Store(cfg.s3)
        for label, key in (("build log", run.build_log_key), ("app log", run.run_log_key)):
            if key and store.exists(key):
                text = store.get_bytes(key).decode("utf-8", errors="replace").strip()
                print(f"\n--- {label} (last 25 lines) ---\n" + "\n".join(text.splitlines()[-25:]))
        if run.vm_id and args.stop_after_run and not args.keep:
            try:
                SandboxClient(cfg.sandbox).destroy(run.vm_id)
                print("\nVM destroyed")
            except SandboxError as exc:
                print(f"\n(could not destroy the VM now: {exc}; the reaper will)")
        elif run.vm_id and args.stop_after_run:
            print(f"\nVM kept: {run.vm_id}")
    _print_results(pool, subject)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
