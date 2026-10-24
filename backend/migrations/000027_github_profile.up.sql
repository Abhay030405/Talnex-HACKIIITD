-- The GitHub profile stage of `recruiter_coding`: the whole public account that owns the resume's repos, not only the
-- repos on the resume (account age, originals vs forks, languages, how steady the last year of commits is). Its facts are
-- one coding_signals row with site 'github'; evidence only, never a verdict.

ALTER TABLE coding_signals DROP CONSTRAINT coding_signals_site_check;
ALTER TABLE coding_signals ADD CONSTRAINT coding_signals_site_check
    CHECK (site IN ('codeforces', 'leetcode', 'codechef', 'github'));

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_coding', 'github_profile', 'go', 'candidate', '{}', 300);
