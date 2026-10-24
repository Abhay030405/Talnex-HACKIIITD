-- The job queue logic lives here, in the database, so Go and Python share one implementation.
-- Workers call these functions; neither language re-implements the rules.

ALTER TABLE jobs
    ADD COLUMN pipeline    text,
    -- Re-running a project bumps this, so a new run gets a fresh set of jobs.
    ADD COLUMN run_number  integer NOT NULL DEFAULT 1,
    -- Same key = same job, so adding a job twice never creates two.
    ADD COLUMN dedupe_key  text,
    ADD COLUMN result      jsonb;
CREATE UNIQUE INDEX jobs_dedupe_idx ON jobs (dedupe_key) WHERE dedupe_key IS NOT NULL;

-- The stage order of each pipeline, as data. A stage starts when every stage in after_stages is done
-- for the same target and run.
CREATE TABLE pipeline_stages (
    pipeline            text NOT NULL,
    stage               text NOT NULL,
    runner              text NOT NULL CHECK (runner IN ('go', 'python')),
    target_type         text NOT NULL CHECK (target_type IN ('project', 'candidate', 'candidate_project', 'event')),
    after_stages        text[] NOT NULL DEFAULT '{}',
    time_limit_seconds  integer NOT NULL DEFAULT 900,
    PRIMARY KEY (pipeline, stage)
);

-- Wake workers the moment a job can be taken. The payload is the runner name.
CREATE FUNCTION notify_job() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('jobs', NEW.runner);
    RETURN NEW;
END $$;

CREATE TRIGGER jobs_notify
    AFTER INSERT OR UPDATE OF status ON jobs
    FOR EACH ROW WHEN (NEW.status IN ('queued', 'retrying'))
    EXECUTE FUNCTION notify_job();

-- Add one job. Returns its id, or NULL if the same job already exists.
CREATE FUNCTION enqueue_job(
    p_job_type            text,
    p_runner              text,
    p_target_type         text,
    p_target_id           uuid,
    p_input               jsonb   DEFAULT '{}',
    p_pipeline            text    DEFAULT NULL,
    p_run_number          integer DEFAULT 1,
    p_time_limit_seconds  integer DEFAULT 900,
    p_max_tries           integer DEFAULT 3
) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO jobs (job_type, runner, target_type, target_id, input, pipeline, run_number,
                      time_limit_seconds, max_tries, dedupe_key)
    VALUES (p_job_type, p_runner, p_target_type, p_target_id, p_input, p_pipeline, p_run_number,
            p_time_limit_seconds, p_max_tries,
            coalesce(p_pipeline, '-') || ':' || p_job_type || ':' || p_target_type || ':' ||
            p_target_id::text || ':' || p_run_number::text)
    ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Start a pipeline for a target: adds every stage that has nothing before it.
CREATE FUNCTION start_pipeline(
    p_pipeline     text,
    p_target_type  text,
    p_target_id    uuid,
    p_run_number   integer DEFAULT 1
) RETURNS SETOF uuid LANGUAGE plpgsql AS $$
DECLARE
    s    pipeline_stages;
    v_id uuid;
BEGIN
    FOR s IN SELECT * FROM pipeline_stages
             WHERE pipeline = p_pipeline AND target_type = p_target_type
               AND cardinality(after_stages) = 0 LOOP
        v_id := enqueue_job(s.stage, s.runner, s.target_type, p_target_id, '{}', p_pipeline,
                            p_run_number, s.time_limit_seconds);
        IF v_id IS NOT NULL THEN
            RETURN NEXT v_id;
        END IF;
    END LOOP;
END $$;

-- Take the next free job for a runner. Locks it so two workers never take the same job.
-- Returns no row when nothing is free.
CREATE FUNCTION take_job(p_runner text, p_worker text) RETURNS SETOF jobs LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    UPDATE jobs
       SET status = 'running', tries = tries + 1, locked_by = p_worker, locked_at = now(),
           updated_at = now()
     WHERE id = (SELECT id FROM jobs
                  WHERE runner = p_runner AND status IN ('queued', 'retrying') AND run_after <= now()
                  ORDER BY run_after, created_at
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1)
    RETURNING *;
END $$;

-- Save a job's result, mark it done and add the next stages, all in one step.
-- A stage with several predecessors is added when the last one finishes.
-- Returns the ids of the jobs it added. Does nothing if the worker no longer holds the job.
CREATE FUNCTION complete_job(p_job_id uuid, p_worker text, p_result jsonb DEFAULT '{}')
RETURNS SETOF uuid LANGUAGE plpgsql AS $$
DECLARE
    j    jobs;
    s    pipeline_stages;
    v_id uuid;
BEGIN
    UPDATE jobs
       SET status = 'done', result = p_result, locked_by = NULL, locked_at = NULL, updated_at = now()
     WHERE id = p_job_id AND status = 'running' AND locked_by = p_worker
    RETURNING * INTO j;
    IF NOT FOUND OR j.pipeline IS NULL THEN
        RETURN;
    END IF;

    -- Two predecessors finishing at the same moment must not both miss each other.
    PERFORM pg_advisory_xact_lock(hashtextextended(j.pipeline || ':' || j.target_id::text, 0));

    FOR s IN SELECT * FROM pipeline_stages
             WHERE pipeline = j.pipeline AND target_type = j.target_type
               AND j.job_type = ANY (after_stages) LOOP
        IF NOT EXISTS (
            SELECT 1 FROM unnest(s.after_stages) AS a
             WHERE NOT EXISTS (
                SELECT 1 FROM jobs d
                 WHERE d.pipeline = j.pipeline AND d.target_type = j.target_type
                   AND d.target_id = j.target_id AND d.run_number = j.run_number
                   AND d.job_type = a AND d.status = 'done')
        ) THEN
            v_id := enqueue_job(s.stage, s.runner, s.target_type, j.target_id, '{}', j.pipeline,
                                j.run_number, s.time_limit_seconds);
            IF v_id IS NOT NULL THEN
                RETURN NEXT v_id;
            END IF;
        END IF;
    END LOOP;
END $$;

-- Record a failure. Retries later (waiting longer each time) until max_tries, then marks it failed.
-- Returns the new status, or NULL if the worker no longer holds the job.
CREATE FUNCTION fail_job(p_job_id uuid, p_worker text, p_error text, p_delay_seconds integer DEFAULT 30)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
BEGIN
    UPDATE jobs
       SET status = CASE WHEN tries < max_tries THEN 'retrying' ELSE 'failed' END,
           error = p_error,
           run_after = now() + make_interval(secs => p_delay_seconds * tries),
           locked_by = NULL, locked_at = NULL, updated_at = now()
     WHERE id = p_job_id AND status = 'running' AND locked_by = p_worker
    RETURNING status INTO v_status;
    RETURN v_status;
END $$;

-- Fail jobs that have been running past their time limit (a crashed worker never reports back).
-- Returns how many it handled.
CREATE FUNCTION reap_stuck_jobs(p_grace_seconds integer DEFAULT 30) RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    r jobs;
    n integer := 0;
BEGIN
    FOR r IN SELECT * FROM jobs
              WHERE status = 'running'
                AND locked_at + make_interval(secs => time_limit_seconds + p_grace_seconds) < now()
              FOR UPDATE SKIP LOCKED LOOP
        PERFORM fail_job(r.id, r.locked_by, 'timed out: past its time limit', 30);
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Pipelines. Stage names are shared across modes (rule: shared parts are designed once).
-- A handler that has nothing to do for a project (for example no live link) finishes with
-- {"skipped": true}, so the next stages still start.
-- Event-level stages (copy between teams, feature comparison) and the candidate-level recruiter
-- stages (resume read, coding profiles, proof report) are added in their own phases.
-- ---------------------------------------------------------------------------------------------

-- End-to-end self test: Python -> Go -> Python.
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages) VALUES
    ('selftest', 'selftest_a', 'python', 'project', '{}'),
    ('selftest', 'selftest_b', 'go',     'project', '{selftest_a}'),
    ('selftest', 'selftest_c', 'python', 'project', '{selftest_b}');

-- Hackathon, per project (architecture section 7, stages 1 to 10).
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages) VALUES
    ('hackathon', 'precheck',      'python', 'project', '{}'),
    ('hackathon', 'video_read',    'python', 'project', '{precheck}'),
    ('hackathon', 'claims',        'python', 'project', '{video_read}'),
    ('hackathon', 'test_plan',     'python', 'project', '{claims}'),
    ('hackathon', 'live_test',     'python', 'project', '{test_plan}'),
    ('hackathon', 'proof_check',   'python', 'project', '{live_test}'),
    ('hackathon', 'github_check',  'go',     'project', '{precheck}'),
    ('hackathon', 'repo_checks',   'python', 'project', '{github_check}'),
    ('hackathon', 'tutorial_copy', 'python', 'project', '{claims}'),
    ('hackathon', 'project_score', 'python', 'project', '{proof_check,repo_checks,tutorial_copy}');

-- Recruiter, per project on the resume (architecture section 8, stages 2 to 6).
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages) VALUES
    ('recruiter', 'precheck',        'python', 'candidate_project', '{}'),
    ('recruiter', 'claims',          'python', 'candidate_project', '{precheck}'),
    ('recruiter', 'test_plan',       'python', 'candidate_project', '{claims}'),
    ('recruiter', 'live_test',       'python', 'candidate_project', '{test_plan}'),
    ('recruiter', 'proof_check',     'python', 'candidate_project', '{live_test}'),
    ('recruiter', 'github_check',    'go',     'candidate_project', '{precheck}'),
    ('recruiter', 'originality',     'python', 'candidate_project', '{github_check,claims}'),
    ('recruiter', 'project_summary', 'python', 'candidate_project', '{proof_check,originality}');
