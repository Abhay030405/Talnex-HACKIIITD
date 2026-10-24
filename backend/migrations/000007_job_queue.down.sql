DROP FUNCTION IF EXISTS reap_stuck_jobs(integer);
DROP FUNCTION IF EXISTS fail_job(uuid, text, text, integer);
DROP FUNCTION IF EXISTS complete_job(uuid, text, jsonb);
DROP FUNCTION IF EXISTS take_job(text, text);
DROP FUNCTION IF EXISTS start_pipeline(text, text, uuid, integer);
DROP FUNCTION IF EXISTS enqueue_job(text, text, text, uuid, jsonb, text, integer, integer, integer);
DROP TRIGGER IF EXISTS jobs_notify ON jobs;
DROP FUNCTION IF EXISTS notify_job();
DROP TABLE IF EXISTS pipeline_stages;
DROP INDEX IF EXISTS jobs_dedupe_idx;
ALTER TABLE jobs DROP COLUMN IF EXISTS result, DROP COLUMN IF EXISTS dedupe_key,
    DROP COLUMN IF EXISTS run_number, DROP COLUMN IF EXISTS pipeline;
