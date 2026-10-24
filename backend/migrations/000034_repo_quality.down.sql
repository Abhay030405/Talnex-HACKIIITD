UPDATE pipeline_stages SET after_stages = array_remove(after_stages, 'repo_quality')
 WHERE (pipeline = 'recruiter' AND stage = 'project_summary') OR (pipeline = 'hackathon' AND stage = 'project_score');
DELETE FROM pipeline_stages WHERE stage = 'repo_quality';
DROP TABLE IF EXISTS repo_quality;
