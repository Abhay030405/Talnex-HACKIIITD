-- What the resume says about each project's dates, team and the candidate's role, read only when written on the resume
-- (never guessed) and editable on the confirm page. Compared with the repository's GitHub history in the report, as
-- evidence beside the score, never subtracted from it. Dates are YYYY or YYYY-MM; the end may be 'present'.
ALTER TABLE candidate_projects ADD COLUMN claimed_start text;
ALTER TABLE candidate_projects ADD COLUMN claimed_end text;
ALTER TABLE candidate_projects ADD COLUMN claimed_team text CHECK (claimed_team IN ('solo', 'team'));
ALTER TABLE candidate_projects ADD COLUMN claimed_team_size integer CHECK (claimed_team_size BETWEEN 1 AND 99);
ALTER TABLE candidate_projects ADD COLUMN claimed_role text;
