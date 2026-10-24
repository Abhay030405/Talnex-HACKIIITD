-- Feature comparison and the AI opinion join the event-level checks (after copy_between_teams).
-- A feature_groups row is either one feature built by several teams ('feature') or "Best Access" and the like ('group', open-theme).
ALTER TABLE feature_groups ADD COLUMN kind text NOT NULL DEFAULT 'feature' CHECK (kind IN ('feature', 'group'));

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon_event', 'feature_compare', 'python', 'event', '{copy_between_teams}', 1800),
    ('hackathon_event', 'ai_opinion',      'python', 'event', '{feature_compare}',     3600);
