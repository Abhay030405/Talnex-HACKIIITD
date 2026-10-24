DELETE FROM pipeline_stages WHERE pipeline = 'recruiter_candidate' AND stage = 'auto_confirm';
DROP INDEX IF EXISTS candidates_role_idx;
ALTER TABLE candidates DROP COLUMN IF EXISTS role_id;
DELETE FROM criteria WHERE role_id IS NOT NULL;
ALTER TABLE criteria DROP CONSTRAINT IF EXISTS criteria_one_owner;
DROP INDEX IF EXISTS criteria_role_idx;
ALTER TABLE criteria DROP COLUMN IF EXISTS role_id;
ALTER TABLE criteria ALTER COLUMN event_id SET NOT NULL;
DROP TABLE IF EXISTS roles;
