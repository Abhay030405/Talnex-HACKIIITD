-- The hackathon's tutorial_copy stage now runs the shared originality checks (repo vs live site, tutorial copy), which read the
-- repository facts saved by github_check, so it waits for that stage too.
UPDATE pipeline_stages SET after_stages = '{claims,github_check}' WHERE pipeline = 'hackathon' AND stage = 'tutorial_copy';
