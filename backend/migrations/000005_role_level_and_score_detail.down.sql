ALTER TABLE results DROP COLUMN IF EXISTS score_breakdown, DROP COLUMN IF EXISTS score_reason;
ALTER TABLE candidates DROP COLUMN IF EXISTS role_level;
ALTER TABLE events DROP COLUMN IF EXISTS role_level;
