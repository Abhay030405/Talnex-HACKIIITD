"""How long a check took and what it cost: only the latest run counts, model and browser are kept apart."""
import uuid

from talnex_ai.reports.run_cost import run_usage


def test_the_latest_run_is_measured_with_model_and_browser_apart(pool):
    target = str(uuid.uuid4())
    with pool.connection() as conn:
        def job(run, stage, started, ended, status="done"):
            return conn.execute(
                """INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, dedupe_key,
                                     created_at, updated_at)
                   VALUES (%s, 'python', 'project', %s::uuid, 'hackathon', %s, %s, %s,
                           now() - %s::interval, now() - %s::interval) RETURNING id""",
                (stage, target, run, status, f"cost:{stage}:{target}:{run}", started, ended)).fetchone()[0]
        old = job(1, "claims", "2 hours", "1 hour")
        claims = job(2, "claims", "300 seconds", "250 seconds")
        live = job(2, "live_test", "250 seconds", "19 seconds")
        conn.execute("""INSERT INTO usage_log (job_id, service, cost_usd) VALUES
                        (%s, 'azure_foundry', 9), (%s, 'azure_foundry', 0.04), (%s, 'azure_foundry', 0.05),
                        (%s, 'tinyfish.main.browser', 0.02)""", (old, claims, live, live))
        run = run_usage(conn, [("project", target)])
        assert run["finished"] is True and 280 <= run["seconds"] <= 282
        assert (run["model_usd"], run["browser_usd"], run["cost_usd"]) == (0.09, 0.02, 0.11)   # the earlier run left out
        assert (run["model_calls"], run["browser_sessions"]) == (2, 1)

        job(3, "precheck", "10 seconds", "5 seconds", status="running")
        assert run_usage(conn, [("project", target)])["finished"] is False   # a run still going reports the time so far

        assert run_usage(conn, [("project", str(uuid.uuid4()))]) is None
        assert run_usage(conn, []) is None
        conn.execute("DELETE FROM jobs WHERE target_id = %s::uuid", (target,))
