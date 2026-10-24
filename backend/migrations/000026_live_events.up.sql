-- What the Python worker is doing, saved for replay: a viewer who opens the live view late sees what already happened.
-- The same events also travel live on pg_notify('live'). A viewing aid only: real results stay in results, steps and scores.
-- Rows older than 7 days are deleted by the cleanup.
CREATE TABLE live_events (
    id            bigserial PRIMARY KEY,
    subject_kind  text NOT NULL,
    subject_id    uuid NOT NULL,
    job_id        uuid,
    kind          text NOT NULL,
    payload       jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX live_events_subject_idx ON live_events (subject_id, id);
CREATE INDEX live_events_created_idx ON live_events (created_at);
