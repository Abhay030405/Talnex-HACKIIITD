-- A candidate-level pipeline for coding profiles (architecture section 8, stage 7, and section 18).
--
-- `recruiter_coding` has one Go stage: `codeforces`. It reads the candidate's Codeforces handle, fetches the public
-- profile and keeps the facts in coding_signals. It is not chained into `recruiter_candidate`; it is started on its own.
-- Data only, no table changes.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_coding', 'codeforces', 'go', 'candidate', '{}', 300);
