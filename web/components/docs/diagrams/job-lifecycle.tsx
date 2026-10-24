'use client';
import { box, Diagram, link } from './diagram';

const nodes = [
  box('start', 0, 0, 'start_pipeline()', 'queues the stages with no after_stages'),
  box('queued', 280, 0, 'queued', 'dedupe_key: same job never twice · pg_notify("jobs")', 'accent'),
  box('take', 560, 0, 'take_job()', 'FOR UPDATE SKIP LOCKED · oldest run_after first'),
  box('running', 840, 0, 'running', 'tries + 1 · locked_by · locked_at', 'accent'),
  box('done', 840, 170, 'complete_job()', 'save result · queue every next stage whose after_stages are all done', 'safe'),
  box('retry', 560, 170, 'retrying', 'fail_job(): run_after = now + delay × tries', 'question'),
  box('failed', 280, 170, 'failed', 'tries reached max_tries', 'danger'),
  box('reap', 0, 170, 'reap_stuck_jobs()', 'running past time limit + grace → retry'),
];

const edges = [
  link('start', 'r', 'queued', 'l'),
  link('queued', 'r', 'take', 'l', 'a worker wakes'),
  link('take', 'r', 'running', 'l'),
  link('running', 'b', 'done', 't', 'handler returns'),
  link('running', 'b', 'retry', 'r', 'error · timeout', 'soft'),
  link('retry', 't', 'take', 'b', 'when run_after passes', 'soft', true),
  link('retry', 'l', 'failed', 'r', 'no tries left', 'soft'),
  link('done', 't', 'queued', 'b', 'next stages', 'yes'),
  link('reap', 't', 'start', 'b', 'worker died', 'soft'),
];

export function JobLifecycle() {
  return (
    <Diagram
      title="The life of a job"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="All of this is SQL functions in Postgres (migration 000007), used the same way by the Go and the Python workers. Finishing a job and queueing the next stages happen in one transaction, so a crash never leaves a pipeline half moved. Only the worker that holds a job can finish or fail it."
    />
  );
}
