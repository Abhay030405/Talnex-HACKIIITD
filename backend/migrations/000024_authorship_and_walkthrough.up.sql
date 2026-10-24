-- Authorship proof (architecture section 30) and the voice walkthrough (section 31).

-- Where a claim's feature lives in the code (stage code_locate, A1). One row per claim; a re-run replaces it.
CREATE TABLE claim_code_maps (
    claim_id      uuid PRIMARY KEY REFERENCES claims(id) ON DELETE CASCADE,
    -- The commit the line ranges belong to, so every proof link opens the same lines later.
    commit_sha    text,
    -- [{"path": "routes/chat.py", "start": 12, "end": 40, "why": "..."}]
    files         jsonb NOT NULL DEFAULT '[]',
    -- route_mapping, code_structure or model
    found_by      text CHECK (found_by IN ('route_mapping', 'code_structure', 'model')),
    confidence    real,
    -- Set when the code could not be traced (section 30.9); never a mark against anyone.
    not_traced_reason  text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- One GitHub account's share of one claim's code (stage authorship_read, A3).
CREATE TABLE authorship (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id              uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    -- A GitHub login, or 'unlinked' for commits whose email is tied to no account.
    account               text NOT NULL,
    -- Share of the feature's current lines, 0 to 1.
    line_share            real NOT NULL CHECK (line_share >= 0 AND line_share <= 1),
    lines                 integer NOT NULL DEFAULT 0,
    commits               integer NOT NULL DEFAULT 0,
    days_spanned          integer NOT NULL DEFAULT 0,
    -- The biggest single commit's share of this account's lines in the feature.
    largest_commit_share  real,
    first_pushed_at       timestamptz,
    last_pushed_at        timestamptz,
    -- push (GitHub's own records) or commit (commit dates only; the card says so)
    date_source           text NOT NULL DEFAULT 'push' CHECK (date_source IN ('push', 'commit')),
    -- Lines owned by reformatting or moved code, shown as "original author not traced".
    reformatted_lines     integer NOT NULL DEFAULT 0,
    moved_lines           integer NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (claim_id, account)
);
CREATE INDEX authorship_claim_idx ON authorship (claim_id);

-- The team's GitHub handles from the hackathon form (optional).
ALTER TABLE projects ADD COLUMN team_github_handles text[] NOT NULL DEFAULT '{}';

-- One question asked about a feature, and its answer (section 31). Private to the owner.
CREATE TABLE walkthroughs (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id              uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    -- The feature the question is about, once known.
    claim_id              uuid REFERENCES claims(id) ON DELETE SET NULL,
    -- Typed text, or the text made from the recorded audio.
    question              text,
    -- R2 key of the recorded question; cleared once the audio is turned into text and deleted.
    audio_key             text,
    status                text NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued', 'answering', 'done', 'failed')),
    -- The walkthrough answer format (section 21): flow, what we saw, missing, label, proof references.
    answer                jsonb,
    error                 text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    answered_at           timestamptz,
    CHECK (num_nonnulls(project_id, candidate_project_id) = 1)
);
CREATE INDEX walkthroughs_project_idx ON walkthroughs (project_id);
CREATE INDEX walkthroughs_candidate_project_idx ON walkthroughs (candidate_project_id);

-- Stages A1-A3 in both pipelines. Code locate waits for route discovery so it can reuse the sandbox's route mapping.
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon', 'code_locate',     'python', 'project', '{route_discovery,github_check}', 1200),
    ('hackathon', 'github_history',  'go',     'project', '{code_locate}',                   900),
    ('hackathon', 'authorship_read', 'python', 'project', '{github_history}',                900),

    ('recruiter', 'code_locate',     'python', 'candidate_project', '{route_discovery,github_check}', 1200),
    ('recruiter', 'github_history',  'go',     'candidate_project', '{code_locate}',                   900),
    ('recruiter', 'authorship_read', 'python', 'candidate_project', '{github_history}',                900);

-- The card and the report wait for authorship, so its flags are ready.
UPDATE pipeline_stages SET after_stages = array_append(after_stages, 'authorship_read')
 WHERE pipeline = 'hackathon' AND stage = 'project_score' AND NOT 'authorship_read' = ANY (after_stages);
UPDATE pipeline_stages SET after_stages = array_append(after_stages, 'authorship_read')
 WHERE pipeline = 'recruiter' AND stage = 'project_summary' AND NOT 'authorship_read' = ANY (after_stages);
