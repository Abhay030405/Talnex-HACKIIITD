-- The two dev pipelines for the sandbox track now run the whole chain, one stage after another:
--   sandbox_run > route_discovery > sandbox_plan > sandbox_test > sandbox_end
-- (the real hackathon and recruiter pipelines get these stages when the track is wired in)

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('sandbox_check_project', 'route_discovery', 'python', 'project', '{sandbox_run}',      900),
    ('sandbox_check_project', 'sandbox_plan',    'python', 'project', '{route_discovery}',  1200),
    ('sandbox_check_project', 'sandbox_test',    'python', 'project', '{sandbox_plan}',     3600),
    ('sandbox_check_project', 'sandbox_end',     'python', 'project', '{sandbox_test}',     300),

    ('sandbox_check', 'route_discovery', 'python', 'candidate_project', '{sandbox_run}',      900),
    ('sandbox_check', 'sandbox_plan',    'python', 'candidate_project', '{route_discovery}',  1200),
    ('sandbox_check', 'sandbox_test',    'python', 'candidate_project', '{sandbox_plan}',     3600),
    ('sandbox_check', 'sandbox_end',     'python', 'candidate_project', '{sandbox_test}',     300);
