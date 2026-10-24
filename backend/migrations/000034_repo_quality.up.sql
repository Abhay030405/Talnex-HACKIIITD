-- The repository judged as engineering work (stage repo_quality, Python): production practices, structure, hygiene,
-- commit style, docs and consistency. One row per area for a resume project or a hackathon project. Evidence only:
-- it never changes a feature score.
CREATE TABLE repo_quality (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            uuid REFERENCES projects(id) ON DELETE CASCADE,
    candidate_project_id  uuid REFERENCES candidate_projects(id) ON DELETE CASCADE,
    area                  text NOT NULL,
    score                 numeric(3,1) NOT NULL CHECK (score BETWEEN 0 AND 10),
    summary               text NOT NULL,
    -- [{kind: file|commit, path | sha + message, note}], always pointing at a real file or commit
    evidence              jsonb NOT NULL DEFAULT '[]',
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK ((project_id IS NULL) <> (candidate_project_id IS NULL))
);
CREATE INDEX repo_quality_project_idx ON repo_quality (project_id);
CREATE INDEX repo_quality_candidate_project_idx ON repo_quality (candidate_project_id);

INSERT INTO pipeline_stages (pipeline, stage, runner, target_type, after_stages, time_limit_seconds) VALUES
    ('recruiter', 'repo_quality', 'python', 'candidate_project', '{github_check}', 600),
    ('hackathon', 'repo_quality', 'python', 'project',           '{github_check}', 600);

-- The report and the card wait for it, so the engineering view is ready with them.
UPDATE pipeline_stages SET after_stages = array_append(after_stages, 'repo_quality')
 WHERE pipeline = 'recruiter' AND stage = 'project_summary' AND NOT 'repo_quality' = ANY (after_stages);
UPDATE pipeline_stages SET after_stages = array_append(after_stages, 'repo_quality')
 WHERE pipeline = 'hackathon' AND stage = 'project_score' AND NOT 'repo_quality' = ANY (after_stages);
