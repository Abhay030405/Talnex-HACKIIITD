'use client';
import { box, Diagram, link } from './diagram';

// The recruiter side as four pipelines. Each box is one job; arrows are after_stages in pipeline_stages.
const nodes = [
  box('read', 0, 0, 'resume_read', 'recruiter_candidate'),
  box('auto', 230, 0, 'auto_confirm', 'Go · starts the checks for a role', 'accent'),
  box('coding', 520, 0, 'coding profiles', 'codeforces · codechef · leetcode · leetcode_replay · github_profile'),
  box('pre', 0, 170, 'precheck', 'free Fetch'),
  box('claims', 200, 170, 'claims', 'resume + README'),
  box('plan', 400, 170, 'test_plan', 'plan + checklist (role brief)'),
  box('live', 600, 170, 'live_test', 'agent in a remote browser', 'accent'),
  box('proof', 800, 170, 'proof_check', '2nd model · never-blame', 'safe'),
  box('score', 1000, 170, 'feature_score', '0–10 per feature'),
  box('gh', 200, 320, 'github_check → originality', 'repo vs live · tutorial copy'),
  box('sb', 520, 320, 'sandbox_run → … → code_review', 'fresh VM · routes · review'),
  box('auth', 860, 320, 'code_locate → authorship', 'who wrote it'),
  box('sum', 1000, 470, 'project_summary', 'partial report · last one starts the report'),
  box('report', 640, 470, 'candidate_report', 'waits for coding · interview kit', 'accent'),
  box('clean', 320, 470, 'resume_cleanup', 'Go · deletes the resume', 'safe'),
];

const edges = [
  link('read', 'r', 'auto', 'l'),
  link('auto', 'r', 'coding', 'l', 'once'),
  link('auto', 'b', 'pre', 't', 'per project'),
  link('pre', 'r', 'claims', 'l'),
  link('claims', 'r', 'plan', 'l'),
  link('plan', 'r', 'live', 'l'),
  link('live', 'r', 'proof', 'l'),
  link('proof', 'r', 'score', 'l'),
  link('pre', 'b', 'gh', 'l', '', 'soft'),
  link('pre', 'b', 'sb', 't', '', 'soft'),
  link('sb', 'r', 'auth', 'l', '', 'soft'),
  link('score', 'b', 'sum', 't'),
  link('auth', 'b', 'sum', 'l', '', 'soft'),
  link('sum', 'l', 'report', 'r', 'all projects done'),
  link('coding', 'b', 'report', 't', 'report waits for these', 'soft', true),
  link('report', 'l', 'clean', 'r'),
];

export function PipelineDag() {
  return (
    <Diagram
      title="Recruiter pipelines"
      nodes={nodes}
      edges={edges}
      size="large"
      caption="One resume becomes four pipelines. Every box is a job in Postgres; a worker that finishes one saves its result and queues the next in the same transaction. Dashed arrows run beside the main line. The hackathon side reuses the per-project stages and adds event stages (copy detection, feature comparison)."
    />
  );
}
