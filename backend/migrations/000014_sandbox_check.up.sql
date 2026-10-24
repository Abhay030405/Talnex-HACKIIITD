-- Two one-stage pipelines for trying the sandbox track on its own (the real hackathon and recruiter pipelines get
-- their sandbox stages when the whole track is wired in). One pipeline per kind of subject, like live_check.
--   sandbox_check_project   (a hackathon project)
--   sandbox_check           (a project on a resume)
-- The stage clones the repo into a throwaway VM, works out how to run it, builds and starts it.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('sandbox_check_project', 'sandbox_run', 'python', 'project',           '{}', 1800),
    ('sandbox_check',         'sandbox_run', 'python', 'candidate_project', '{}', 1800);
