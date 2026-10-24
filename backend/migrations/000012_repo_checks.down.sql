UPDATE pipeline_stages SET after_stages = '{github_check}'
 WHERE pipeline = 'hackathon' AND stage = 'repo_checks';

DELETE FROM pipeline_stages WHERE pipeline = 'hackathon' AND stage IN ('event_dates', 'sponsor_files');
