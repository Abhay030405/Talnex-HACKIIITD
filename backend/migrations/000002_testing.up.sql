-- Claims, test runs, steps and results.
-- A "subject" is either a hackathon project or a recruiter's candidate project.
-- Exactly one of project_id / candidate_project_id is set, so shared code never asks which mode it is in.

CREATE TABLE claims (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    text                  text NOT NULL,
    -- Access, Core, Logic, Reliability, Setup, Edge cases, or an organizer criterion name. Data, not a fixed list.
    claim_group           text NOT NULL,
    importance            smallint NOT NULL CHECK (importance IN (1, 2, 3)),
    source                text NOT NULL CHECK (source IN ('video', 'criteria', 'resume', 'readme', 'route')),
    -- live, sandbox, or both
    track                 text NOT NULL DEFAULT 'live' CHECK (track IN ('live', 'sandbox', 'both')),
    testable              boolean NOT NULL DEFAULT true,
    untestable_reason     text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(project_id, candidate_project_id) = 1)
);
CREATE INDEX claims_project_idx ON claims (project_id);
CREATE INDEX claims_candidate_project_idx ON claims (candidate_project_id);

-- One agent run (or one sandbox run) for a claim.
CREATE TABLE test_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id      uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    try_number    smallint NOT NULL DEFAULT 1,
    track         text NOT NULL CHECK (track IN ('live', 'sandbox')),
    test_type     text NOT NULL CHECK (test_type IN ('normal', 'demo_replay', 'known_answer',
                                                     'repeat', 'bad_input', 'access',
                                                     'setup', 'route_smoke', 'edge_case',
                                                     'light_load', 'repo_tests')),
    -- How the test was done (for example login step used, or backup method)
    method        text,
    started_at    timestamptz,
    ended_at      timestamptz,
    outcome       text CHECK (outcome IN ('passed', 'failed', 'blocked', 'error'))
);
CREATE INDEX test_runs_claim_idx ON test_runs (claim_id);

-- One step inside a run. screen = screenshot, http = request/response, command = command output.
CREATE TABLE steps (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       uuid NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    step_number  integer NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('screen', 'http', 'command')),
    action       text NOT NULL,
    expected     text,
    observed     text,
    -- R2 key of the screenshot, request/response record, or command output
    proof_key    text,
    duration_ms  integer,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, step_number)
);

-- Final result for a claim.
CREATE TABLE results (
    claim_id               uuid PRIMARY KEY REFERENCES claims(id) ON DELETE CASCADE,
    verdict                text NOT NULL CHECK (verdict IN ('works', 'partly_works', 'broken',
                                                            'could_not_test', 'reviewed_from_code')),
    confidence             text NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'disagree')),
    reason                 text,
    checker_view           text,
    second_model_agreed    boolean,
    proof_keys             text[] NOT NULL DEFAULT '{}',
    -- Per-feature score out of 10. Left empty until the scoring formula is decided.
    feature_score          numeric(3,1) CHECK (feature_score BETWEEN 0 AND 10),
    created_at             timestamptz NOT NULL DEFAULT now()
);
