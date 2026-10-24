UPDATE pipeline_stages SET after_stages = array_remove(after_stages, 'authorship_read')
 WHERE (pipeline = 'hackathon' AND stage = 'project_score') OR (pipeline = 'recruiter' AND stage = 'project_summary');
DELETE FROM pipeline_stages
 WHERE pipeline IN ('hackathon', 'recruiter') AND stage IN ('code_locate', 'github_history', 'authorship_read');
DROP TABLE IF EXISTS walkthroughs;
ALTER TABLE projects DROP COLUMN IF EXISTS team_github_handles;
DROP TABLE IF EXISTS authorship;
DROP TABLE IF EXISTS claim_code_maps;
