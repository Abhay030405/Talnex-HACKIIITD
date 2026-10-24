-- The Python `leetcode_replay` stage of the candidate-level `recruiter_coding` pipeline (architecture section 18): reads
-- the candidate's public LeetCode Code Replay and keeps suspicious pastes in coding_signals. No predecessors, so it runs
-- beside `codeforces`, `codechef` and `leetcode`. Data only, no table changes.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_coding', 'leetcode_replay', 'python', 'candidate', '{}', 600);
