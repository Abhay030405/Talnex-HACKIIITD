'use client';
import { box, Diagram, link } from './diagram';

const nodes = [
  box('role', 0, 0, 'Create a role', 'job description · person · skills · weights · checks', 'accent'),
  box('upload', 280, 0, 'Upload resumes', 'one or many, sent one by one'),
  box('auto', 560, 0, 'Auto-confirm', 'what the reader found starts the checks'),
  box('run', 840, 0, 'Checks run', 'only the chosen checks · live view · live wall'),
  box('partial', 840, 160, 'Results so far', 'a partial report after each project'),
  box('report', 560, 160, 'Final report', 'scores · proof · fit to role · weighted · interview kit', 'accent'),
  box('weights', 280, 160, 'Change weights', 're-scores at once, no re-test', 'safe'),
  box('ask', 0, 160, 'Ask TalNex / re-run', 're-test a project · coding again · custom test', 'question'),
];

const edges = [
  link('role', 'r', 'upload', 'l'),
  link('upload', 'r', 'auto', 'l'),
  link('auto', 'r', 'run', 'l'),
  link('run', 'b', 'partial', 't', 'as each project ends', 'soft'),
  link('partial', 'l', 'report', 'r', 'last project'),
  link('report', 'l', 'weights', 'r', '', 'soft'),
  link('report', 'b', 'ask', 'b', '', 'soft'),
  link('ask', 't', 'run', 't', 'a new run', 'soft', true),
];

export function RecruiterFlow() {
  return (
    <Diagram
      title="Recruiter flow"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="A role holds what the recruiter is hiring for and is shared by every resume uploaded to it. The job description shapes what is checked, never whether a feature works: feature scores stay proof-only."
    />
  );
}
