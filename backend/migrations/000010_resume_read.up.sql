-- A candidate-level pipeline for the recruiter side (architecture section 8, stage 1).
--
-- `recruiter_candidate` has one stage: `resume_read`. It reads the resume PDF, saves the projects on it, and starts
-- the per-project `recruiter` pipeline for each one. Data only, no table changes.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_candidate', 'resume_read', 'python', 'candidate', '{}', 600);
