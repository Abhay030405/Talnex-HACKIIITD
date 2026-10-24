DELETE FROM coding_signals WHERE site = 'leetcode' AND signal IN ('leetcode_replay', 'leetcode_paste');
DELETE FROM pipeline_stages WHERE pipeline = 'recruiter_coding' AND stage = 'leetcode_replay';
