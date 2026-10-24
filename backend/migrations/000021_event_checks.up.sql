-- The event-level checks. Started by the report stage of the last team of an event (one run when every team is done).
-- First: copying between teams.
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon_event', 'copy_between_teams', 'python', 'event', '{}', 3600);
