-- The two Python stages of the candidate-level `recruiter_coding` pipeline (created in 000011, which has the Go
-- `codeforces` stage): public CodeChef and LeetCode profile facts, read with the free TinyFish Fetch. No predecessors,
-- so all three run side by side. Data only, no table changes.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_coding', 'codechef', 'python', 'candidate', '{}', 300),
    ('recruiter_coding', 'leetcode', 'python', 'candidate', '{}', 300);
