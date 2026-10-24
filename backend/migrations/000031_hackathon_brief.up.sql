-- Hackathon side of roles: judges give the event a brief (the problem statement or theme) and choose which checks run;
-- each team can add an abstract. Both reach the same prompts as a recruiter's role brief. Empty means as before.
ALTER TABLE events ADD COLUMN brief text NOT NULL DEFAULT '';
ALTER TABLE events ADD COLUMN checks jsonb NOT NULL DEFAULT '{}';
ALTER TABLE projects ADD COLUMN abstract text NOT NULL DEFAULT '';
