-- The sandbox track joins the real pipelines, for hackathon projects and for projects on a resume alike.
--
--   precheck > sandbox_run (clone, build, start) ----------------------------+
--   claims  > route_discovery > sandbox_plan > sandbox_test > repo_tests      |
--                             > code_review > sandbox_end ---+                |
--   test_plan > live_test > proof_check -----------------------> track_reconcile > feature_score > (project_score | project_summary)
--
-- A project with no repository link makes every sandbox stage end as "skipped", so nothing waits on it.
-- track_reconcile makes a claim tried by both the live site and the repository tests agree (or become "could not confirm").
-- Data only: no table changes.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon', 'sandbox_run',      'python', 'project', '{precheck}',                 1800),
    ('hackathon', 'route_discovery',  'python', 'project', '{sandbox_run,claims}',        900),
    ('hackathon', 'sandbox_plan',     'python', 'project', '{route_discovery}',          1200),
    ('hackathon', 'sandbox_test',     'python', 'project', '{sandbox_plan}',             3600),
    ('hackathon', 'repo_tests',       'python', 'project', '{sandbox_test}',             1800),
    ('hackathon', 'code_review',      'python', 'project', '{repo_tests}',               1800),
    ('hackathon', 'sandbox_end',      'python', 'project', '{code_review}',               300),
    ('hackathon', 'track_reconcile',  'python', 'project', '{proof_check,sandbox_end}',   600),

    ('recruiter', 'sandbox_run',      'python', 'candidate_project', '{precheck}',                 1800),
    ('recruiter', 'route_discovery',  'python', 'candidate_project', '{sandbox_run,claims}',        900),
    ('recruiter', 'sandbox_plan',     'python', 'candidate_project', '{route_discovery}',          1200),
    ('recruiter', 'sandbox_test',     'python', 'candidate_project', '{sandbox_plan}',             3600),
    ('recruiter', 'repo_tests',       'python', 'candidate_project', '{sandbox_test}',             1800),
    ('recruiter', 'code_review',      'python', 'candidate_project', '{repo_tests}',               1800),
    ('recruiter', 'sandbox_end',      'python', 'candidate_project', '{code_review}',               300),
    ('recruiter', 'track_reconcile',  'python', 'candidate_project', '{proof_check,sandbox_end}',   600);

UPDATE pipeline_stages SET after_stages = '{track_reconcile}'
 WHERE stage = 'feature_score' AND pipeline IN ('hackathon', 'recruiter');
