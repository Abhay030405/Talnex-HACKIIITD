UPDATE pipeline_stages SET time_limit_seconds = 900
 WHERE stage = 'live_test' AND pipeline IN ('hackathon', 'recruiter');

UPDATE pipeline_stages SET after_stages = '{proof_check,originality}'
 WHERE pipeline = 'recruiter' AND stage = 'project_summary';

UPDATE pipeline_stages SET after_stages = '{proof_check,repo_checks,tutorial_copy}'
 WHERE pipeline = 'hackathon' AND stage = 'project_score';

DELETE FROM pipeline_stages WHERE pipeline IN ('live_check', 'live_check_project');
DELETE FROM pipeline_stages WHERE stage = 'feature_score' AND pipeline IN ('hackathon', 'recruiter');
