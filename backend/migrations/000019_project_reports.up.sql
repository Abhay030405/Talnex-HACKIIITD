-- The hackathon proof card. One card per project; building it again after a re-run replaces it.
CREATE TABLE project_reports (
    project_id    uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    report        jsonb NOT NULL,
    has_gaps      boolean NOT NULL DEFAULT false,
    generated_at  timestamptz NOT NULL DEFAULT now()
);

-- The last stage of a hackathon project: build and save the card once the scores are done.
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('hackathon', 'project_report', 'python', 'project', '{project_score}', 600);
