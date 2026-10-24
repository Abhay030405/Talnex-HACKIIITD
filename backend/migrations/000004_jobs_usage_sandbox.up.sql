-- The job queue, usage log and sandbox runs.

-- The queue. Workers of one runner (go or python) take the next free job.
CREATE TABLE jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type            text NOT NULL,
    runner              text NOT NULL CHECK (runner IN ('go', 'python')),
    -- What the job is about: project, candidate, candidate_project, event
    target_type         text NOT NULL CHECK (target_type IN ('project', 'candidate', 'candidate_project', 'event')),
    target_id           uuid NOT NULL,
    input               jsonb NOT NULL DEFAULT '{}',
    status              text NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued', 'running', 'done', 'failed', 'retrying')),
    tries               integer NOT NULL DEFAULT 0,
    max_tries           integer NOT NULL DEFAULT 3,
    time_limit_seconds  integer NOT NULL DEFAULT 900,
    error               text,
    -- A retrying job is not taken before this time
    run_after           timestamptz NOT NULL DEFAULT now(),
    locked_by           text,
    locked_at           timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
-- Fast lookup of the next free job for a runner.
CREATE INDEX jobs_next_idx ON jobs (runner, run_after) WHERE status IN ('queued', 'retrying');
CREATE INDEX jobs_target_idx ON jobs (target_type, target_id);

-- One model call or agent run.
CREATE TABLE usage_log (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        uuid REFERENCES jobs(id) ON DELETE SET NULL,
    service       text NOT NULL,
    model         text,
    tokens_in     integer,
    tokens_out    integer,
    duration_ms   integer,
    cost_usd      numeric(10,5),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_log_job_idx ON usage_log (job_id);

-- One VM run of a repo.
CREATE TABLE sandbox_runs (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    -- Stack, install and start commands, port, health path, services, source, confidence
    recipe                jsonb NOT NULL DEFAULT '{}',
    image                 text,
    status                text NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'building', 'running', 'done',
                                            'could_not_run', 'failed')),
    status_detail         text,
    build_log_key         text,
    run_log_key           text,
    resources             jsonb NOT NULL DEFAULT '{}',
    started_at            timestamptz,
    ended_at              timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(project_id, candidate_project_id) = 1)
);
