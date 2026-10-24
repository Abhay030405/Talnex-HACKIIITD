-- People, events, projects and candidates.

CREATE TABLE users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text NOT NULL UNIQUE,
    name        text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE events (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL REFERENCES users(id),
    name           text NOT NULL,
    mode           text NOT NULL CHECK (mode IN ('open_theme', 'fixed_problem')),
    starts_at      timestamptz NOT NULL,
    ends_at        timestamptz NOT NULL,
    sponsor_tools  text[] NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at)
);
CREATE INDEX events_owner_idx ON events (owner_id);

-- Fixed-problem events only.
CREATE TABLE criteria (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name         text NOT NULL,
    description  text,
    weight       numeric(6,2) NOT NULL CHECK (weight > 0)
);
CREATE INDEX criteria_event_idx ON criteria (event_id);

-- One hackathon submission. A project may have a live link, a repo, or both.
CREATE TABLE projects (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id          uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    team_name         text NOT NULL,
    video_url         text,
    live_url          text,
    repo_url          text,
    -- Reference to the test login kept in TinyFish Vault. Never the login itself.
    test_login_ref    text,
    status            text NOT NULL DEFAULT 'submitted'
                      CHECK (status IN ('submitted', 'prechecking', 'reading', 'testing',
                                        'checking', 'scoring', 'done', 'done_with_gaps', 'failed')),
    status_detail     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX projects_event_idx ON projects (event_id);

-- One recruiter check of one candidate.
CREATE TABLE candidates (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           uuid NOT NULL REFERENCES users(id),
    label              text,
    -- R2 key of the resume PDF. Cleared when the resume is deleted after the report.
    resume_key         text,
    -- {"codeforces": "...", "leetcode": "...", "codechef": "..."}
    coding_handles     jsonb NOT NULL DEFAULT '{}',
    status             text NOT NULL DEFAULT 'submitted'
                       CHECK (status IN ('submitted', 'reading', 'prechecking', 'testing',
                                         'checking', 'reporting', 'done', 'done_with_gaps', 'failed')),
    status_detail      text,
    resume_deleted_at  timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX candidates_owner_idx ON candidates (owner_id);

-- One project listed on a resume.
CREATE TABLE candidate_projects (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id  uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    name          text NOT NULL,
    bullets       text[] NOT NULL DEFAULT '{}',
    live_url      text,
    repo_url      text,
    video_url     text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX candidate_projects_candidate_idx ON candidate_projects (candidate_id);
