UPDATE candidates SET status = 'reading' WHERE status = 'awaiting_confirmation';

ALTER TABLE candidates DROP COLUMN coding_links;

ALTER TABLE candidates DROP CONSTRAINT candidates_status_check;
ALTER TABLE candidates ADD CONSTRAINT candidates_status_check
    CHECK (status IN ('submitted', 'reading', 'prechecking', 'testing',
                      'checking', 'reporting', 'done', 'done_with_gaps', 'failed'));
