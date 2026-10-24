-- A candidate's overall TalNex score (weighted across their projects) belongs to the candidate itself.
ALTER TABLE scores ADD COLUMN candidate_id uuid REFERENCES candidates(id) ON DELETE CASCADE;
ALTER TABLE scores DROP CONSTRAINT scores_check;
ALTER TABLE scores ADD CONSTRAINT scores_subject_check
    CHECK (num_nonnulls(project_id, candidate_project_id, candidate_id) = 1);
CREATE UNIQUE INDEX scores_candidate_group_idx
    ON scores (candidate_id, score_group) WHERE candidate_id IS NOT NULL;
