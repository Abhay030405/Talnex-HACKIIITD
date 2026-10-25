'use client';
import { box, Diagram, link } from './diagram';

// docs/talnex_architecture.md section 11: all four must hold before a claim is marked Broken.
const nodes = [
  box('fail', 260, 0, 'A step did not work', 'the expected result was not on screen'),
  box('q1', 260, 120, 'Did the page actually load?', 'a Fetch check', 'question'),
  box('q2', 260, 240, 'Still failing after ~1 minute?', 'free hosting may have been asleep', 'question'),
  box('q3', 260, 360, 'A second try, a different way, also fails?', undefined, 'question'),
  box('q4', 260, 480, 'An independent check of the screenshots agrees?', 'sees only the screenshots and the expected result', 'question'),
  box('broken', 260, 610, 'Broken', 'with every screenshot as proof', 'danger'),
  box('retest', -60, 240, 'Retest and continue', 'it works after all'),
  box('unsure', 600, 300, 'Could not confirm', 'left out of the score, reason shown, never "fake"', 'safe'),
];

const edges = [
  link('fail', 'b', 'q1', 't'),
  link('q1', 'b', 'q2', 't', 'yes'),
  link('q2', 'b', 'q3', 't', 'yes'),
  link('q3', 'b', 'q4', 't', 'yes'),
  link('q4', 'b', 'broken', 't', 'yes', 'yes'),
  link('q1', 'r', 'unsure', 't', 'no', 'soft'),
  link('q3', 'r', 'unsure', 'l', 'no', 'soft'),
  link('q4', 'r', 'unsure', 'b', 'no', 'soft'),
  link('q2', 'l', 'retest', 'r', 'no', 'soft'),
];

export function NeverBlameLadder() {
  return (
    <Diagram
      title="The never-blame ladder"
      nodes={nodes}
      edges={edges}
      size="large"
      caption="A claim is only Broken when all four steps say so. Anything less is 'could not confirm', which never counts against a team. watch_live never shows 'broken' before the verdict arrives."
    />
  );
}
