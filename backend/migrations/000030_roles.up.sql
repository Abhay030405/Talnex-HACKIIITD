-- Roles: a job opening a recruiter checks candidates against. One role holds the job description, the kind of person
-- wanted, the must-have skills, the judging criteria with their weights, and which checks to run; many resumes can be
-- uploaded to it (bulk upload). A candidate without a role is checked exactly as before.

CREATE TABLE roles (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         uuid NOT NULL REFERENCES users(id),
    title            text NOT NULL,
    job_description  text NOT NULL DEFAULT '',
    person_wanted    text NOT NULL DEFAULT '',
    skills           text[] NOT NULL DEFAULT '{}',
    role_level       text NOT NULL DEFAULT 'fresher' CHECK (role_level IN ('fresher', 'junior', 'mid', 'senior')),
    -- Which checks run, for example {"live_test": true, "coding_profiles": false}. Empty means every check.
    checks           jsonb NOT NULL DEFAULT '{}',
    -- Start the checks on what the resume reader found, without waiting on the confirm page (for bulk uploads).
    auto_confirm     boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX roles_owner_idx ON roles (owner_id);

-- Judging criteria now belong to an event (hackathon) or to a role (recruiter), never both.
ALTER TABLE criteria ALTER COLUMN event_id DROP NOT NULL;
ALTER TABLE criteria ADD COLUMN role_id uuid REFERENCES roles(id) ON DELETE CASCADE;
ALTER TABLE criteria ADD CONSTRAINT criteria_one_owner CHECK ((event_id IS NULL) <> (role_id IS NULL));
CREATE INDEX criteria_role_idx ON criteria (role_id);

ALTER TABLE candidates ADD COLUMN role_id uuid REFERENCES roles(id) ON DELETE SET NULL;
CREATE INDEX candidates_role_idx ON candidates (role_id);

-- A Go stage after the resume read: for a candidate whose role has auto_confirm, it confirms what was found and starts
-- the checks (the same code as the confirm page). Without a role, or with auto_confirm off, it does nothing.
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_candidate', 'auto_confirm', 'go', 'candidate', '{resume_read}', 120);
