-- Guided tour walkthrough (architecture section 32): a chat beside the live site, where one agent reads the code
-- and another shows the feature in the browser. Private to the owner.

-- One tour chat for a project or a resume project.
CREATE TABLE tour_sessions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id              uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    -- The read-only code VM of this chat and when the host's reaper removes it; empty until the first answer.
    vm_id                 text,
    vm_expires_at         timestamptz,
    -- The commit of the code in the VM, so every proof link of the chat opens the same lines.
    commit_sha            text,
    -- Browser sessions this chat has used (they count toward the project's agent runs).
    browser_runs          integer NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(project_id, candidate_project_id) = 1)
);
CREATE INDEX tour_sessions_project_idx ON tour_sessions (project_id, created_at);
CREATE INDEX tour_sessions_candidate_project_idx ON tour_sessions (candidate_project_id, created_at);

-- One turn of the chat: the question and the guide's reply.
CREATE TABLE tour_messages (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   uuid NOT NULL REFERENCES tour_sessions(id) ON DELETE CASCADE,
    question     text NOT NULL,
    status       text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'working', 'done', 'failed')),
    -- {"say": [{"text", "proof": [...]}], "label": "..."}: what was said, each sentence with its proof (section 32.3).
    answer       jsonb,
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    answered_at  timestamptz
);
CREATE INDEX tour_messages_session_idx ON tour_messages (session_id, created_at);
