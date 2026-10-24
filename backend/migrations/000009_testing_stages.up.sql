-- Wires the shared live-testing stages into the pipelines (data only, no table changes).
--
-- * Adds a `feature_score` stage after `proof_check` in the hackathon and recruiter pipelines, and makes the
--   final stage (project_score / project_summary) wait for it.
-- * Gives `live_test` a longer time limit: it tests every claim of a project, several at a time.
-- * Adds two small pipelines for trying the testing engine on its own, one per kind of subject:
--     live_check          (a project on a resume)  precheck > test_plan > live_test > proof_check > feature_score
--     live_check_project  (a hackathon project)    the same stages
--
-- The claims stage is not part of these small pipelines: the claims are saved first by whoever starts them.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon', 'feature_score', 'python', 'project',           '{proof_check}', 900),
    ('recruiter', 'feature_score', 'python', 'candidate_project', '{proof_check}', 900),

    ('live_check', 'precheck',      'python', 'candidate_project', '{}',              300),
    ('live_check', 'test_plan',     'python', 'candidate_project', '{precheck}',      600),
    ('live_check', 'live_test',     'python', 'candidate_project', '{test_plan}',     3600),
    ('live_check', 'proof_check',   'python', 'candidate_project', '{live_test}',     600),
    ('live_check', 'feature_score', 'python', 'candidate_project', '{proof_check}',   900),

    ('live_check_project', 'precheck',      'python', 'project', '{}',              300),
    ('live_check_project', 'test_plan',     'python', 'project', '{precheck}',      600),
    ('live_check_project', 'live_test',     'python', 'project', '{test_plan}',     3600),
    ('live_check_project', 'proof_check',   'python', 'project', '{live_test}',     600),
    ('live_check_project', 'feature_score', 'python', 'project', '{proof_check}',   900);

UPDATE pipeline_stages SET after_stages = '{feature_score,repo_checks,tutorial_copy}'
 WHERE pipeline = 'hackathon' AND stage = 'project_score';

UPDATE pipeline_stages SET after_stages = '{feature_score,originality}'
 WHERE pipeline = 'recruiter' AND stage = 'project_summary';

UPDATE pipeline_stages SET time_limit_seconds = 3600
 WHERE stage = 'live_test' AND pipeline IN ('hackathon', 'recruiter');
