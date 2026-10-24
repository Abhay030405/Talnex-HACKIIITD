-- Two Go stages for hackathon projects that use the event's own dates and sponsor tools. They only read facts from
-- GitHub; the Python `repo_checks` stage waits for both, then reads the facts and raises the flags.

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon', 'event_dates',   'go', 'project', '{github_check}', 300),
    ('hackathon', 'sponsor_files', 'go', 'project', '{github_check}', 300);

UPDATE pipeline_stages SET after_stages = '{event_dates,sponsor_files}'
 WHERE pipeline = 'hackathon' AND stage = 'repo_checks';
