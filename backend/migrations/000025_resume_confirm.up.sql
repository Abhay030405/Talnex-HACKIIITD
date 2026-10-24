-- Recruiter form in two stages: after the resume is read, the check waits for the recruiter to confirm what was found
-- (projects and coding profiles) before any test runs.
--
-- `awaiting_confirmation` is that waiting state. `coding_links` keeps the profile link as written on the resume
-- ({"leetcode": "https://leetcode.com/u/name"}); `coding_handles` stays the one the coding checks read.

ALTER TABLE candidates DROP CONSTRAINT candidates_status_check;
ALTER TABLE candidates ADD CONSTRAINT candidates_status_check
    CHECK (status IN ('submitted', 'reading', 'awaiting_confirmation', 'prechecking', 'testing',
                      'checking', 'reporting', 'done', 'done_with_gaps', 'failed'));

ALTER TABLE candidates ADD COLUMN coding_links jsonb NOT NULL DEFAULT '{}';
