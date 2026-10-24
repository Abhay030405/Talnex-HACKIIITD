DELETE FROM pipeline_stages WHERE pipeline = 'recruiter_coding' AND stage = 'github_profile';
DELETE FROM coding_signals WHERE site = 'github';
ALTER TABLE coding_signals DROP CONSTRAINT coding_signals_site_check;
ALTER TABLE coding_signals ADD CONSTRAINT coding_signals_site_check
    CHECK (site IN ('codeforces', 'leetcode', 'codechef'));
