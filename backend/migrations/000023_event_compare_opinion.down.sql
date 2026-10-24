DELETE FROM pipeline_stages WHERE pipeline = 'hackathon_event' AND stage IN ('feature_compare', 'ai_opinion');
ALTER TABLE feature_groups DROP COLUMN kind;
