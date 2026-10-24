-- Role level decides how feature scores are weighted (architecture section 29).
ALTER TABLE events
    ADD COLUMN role_level text NOT NULL DEFAULT 'fresher'
    CHECK (role_level IN ('fresher', 'junior', 'mid', 'senior'));

ALTER TABLE candidates
    ADD COLUMN role_level text NOT NULL DEFAULT 'fresher'
    CHECK (role_level IN ('fresher', 'junior', 'mid', 'senior'));

-- One-line reason for the feature score, and the checklist + part scores behind it.
ALTER TABLE results
    ADD COLUMN score_reason text,
    ADD COLUMN score_breakdown jsonb NOT NULL DEFAULT '{}';
