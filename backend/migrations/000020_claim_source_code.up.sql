-- Claims can come from the project's own code: features found by reading the frontend and backend, each with the file and line
-- that show it exists (this replaces reading a demo video for open-theme events).
ALTER TABLE claims DROP CONSTRAINT claims_source_check;
ALTER TABLE claims ADD CONSTRAINT claims_source_check
    CHECK (source IN ('video', 'criteria', 'resume', 'readme', 'route', 'code'));
