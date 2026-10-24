-- Phase 4: the recruiter proof report. One report per candidate; building it again replaces it.
CREATE TABLE candidate_reports (
    candidate_id  uuid PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
    report        jsonb NOT NULL,
    has_gaps      boolean NOT NULL DEFAULT false,
    generated_at  timestamptz NOT NULL DEFAULT now()
);

-- The pipeline that builds the report and then deletes the resume. Started by project_summary of the last project.
INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter_report', 'candidate_report', 'python', 'candidate', '{}',                 600),
    ('recruiter_report', 'resume_cleanup',   'go',     'candidate', '{candidate_report}', 300);
