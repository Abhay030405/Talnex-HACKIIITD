UPDATE pipeline_stages SET after_stages = '{proof_check}'
 WHERE stage = 'feature_score' AND pipeline IN ('hackathon', 'recruiter');

DELETE FROM pipeline_stages
 WHERE pipeline IN ('hackathon', 'recruiter')
   AND stage IN ('sandbox_run', 'route_discovery', 'sandbox_plan', 'sandbox_test', 'repo_tests', 'code_review', 'sandbox_end', 'track_reconcile');
