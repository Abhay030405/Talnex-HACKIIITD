DROP INDEX IF EXISTS scores_candidate_group_idx;
ALTER TABLE scores DROP CONSTRAINT IF EXISTS scores_subject_check;
ALTER TABLE scores DROP COLUMN IF EXISTS candidate_id;
ALTER TABLE scores ADD CONSTRAINT scores_check CHECK (num_nonnulls(project_id, candidate_project_id) = 1);
