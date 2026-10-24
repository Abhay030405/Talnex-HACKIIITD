-- Flags, scores, opinions, feature comparison, copy checks and coding signals.

CREATE TABLE flags (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    candidate_id          uuid REFERENCES candidates(id) ON DELETE CASCADE,
    flag_type             text NOT NULL,
    level                 text NOT NULL CHECK (level IN ('info', 'review', 'strong')),
    reason                text NOT NULL,
    -- Links, files, dates, screenshot keys
    evidence              jsonb NOT NULL DEFAULT '{}',
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(project_id, candidate_project_id, candidate_id) = 1)
);

-- Group score. Works for projects and for candidate projects, so the recruiter side can show them too.
CREATE TABLE scores (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    score_group           text NOT NULL,
    -- 0 to 100 as in the architecture; the website can show it as x/10
    score                 numeric(5,2) CHECK (score BETWEEN 0 AND 100),
    coverage              numeric(5,2) NOT NULL CHECK (coverage BETWEEN 0 AND 100),
    confidence            text NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    claims_used           integer NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(project_id, candidate_project_id) = 1)
);
CREATE UNIQUE INDEX scores_project_group_idx
    ON scores (project_id, score_group) WHERE project_id IS NOT NULL;
CREATE UNIQUE INDEX scores_candidate_project_group_idx
    ON scores (candidate_project_id, score_group) WHERE candidate_project_id IS NOT NULL;

-- AI opinion: UI or innovation. Never part of the score.
CREATE TABLE opinions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind         text NOT NULL CHECK (kind IN ('ui', 'innovation')),
    -- Each part: score 1-5, one-line reason, screenshot key, whether the models disagreed
    parts        jsonb NOT NULL,
    models       text[] NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, kind)
);

CREATE TABLE feature_groups (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id      uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    feature_name  text NOT NULL,
    claim_ids     uuid[] NOT NULL DEFAULT '{}',
    -- Top teams that built it best, with reasons and screenshot keys
    best_teams    jsonb NOT NULL DEFAULT '[]',
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feature_groups_event_idx ON feature_groups (event_id);

CREATE TABLE copy_pairs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id          uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    project_a_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    project_b_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    shared_pct        numeric(5,2) NOT NULL CHECK (shared_pct BETWEEN 0 AND 100),
    level             text CHECK (level IN ('info', 'review', 'strong')),
    matching_files    jsonb NOT NULL DEFAULT '[]',
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (project_a_id <> project_b_id),
    UNIQUE (project_a_id, project_b_id)
);
CREATE INDEX copy_pairs_event_idx ON copy_pairs (event_id);

CREATE TABLE coding_signals (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id   uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    site           text NOT NULL CHECK (site IN ('codeforces', 'leetcode', 'codechef')),
    contest        text,
    problem        text,
    signal         text NOT NULL,
    weight         text NOT NULL CHECK (weight IN ('not_suspicious', 'medium', 'strong')),
    -- Seconds into the replay, so a recruiter can watch those seconds
    replay_time_s  integer,
    evidence       jsonb NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX coding_signals_candidate_idx ON coding_signals (candidate_id);
