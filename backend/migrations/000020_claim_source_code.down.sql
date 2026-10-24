DELETE FROM claims WHERE source = 'code';
ALTER TABLE claims DROP CONSTRAINT claims_source_check;
ALTER TABLE claims ADD CONSTRAINT claims_source_check
    CHECK (source IN ('video', 'criteria', 'resume', 'readme', 'route'));
