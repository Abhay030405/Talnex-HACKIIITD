'use client';
import { box, Diagram, link } from './diagram';

const nodes = [
  box('q', 0, 0, 'Question in the chat', 'candidate or hackathon project'),
  box('job', 270, 0, 'report_answer job', 'saved report + role brief + last 6 turns, as data'),
  box('answer', 560, 0, 'Answer + one action?', 'from the proof only · never ranks', 'question'),
  box('btn', 560, 160, 'Button in the chat', 'the reviewer presses it; nothing runs alone', 'safe'),
  box('rerun', 0, 300, 'Re-test / re-run', 'a new run of the pipeline'),
  box('weight', 280, 300, 'Change a weight', 'opens the settings'),
  box('custom', 560, 300, 'custom_test job', 'your words → one-off plan → live run', 'accent'),
  box('back', 840, 300, 'Result in the chat', 'verdict · what it saw · screenshots · no score change'),
];

const edges = [
  link('q', 'r', 'job', 'l', 'queued'),
  link('job', 'r', 'answer', 'l'),
  link('answer', 'b', 'btn', 't', 'if an action fits'),
  link('btn', 'l', 'rerun', 't'),
  link('btn', 'b', 'weight', 't'),
  link('btn', 'b', 'custom', 't'),
  link('custom', 'r', 'back', 'l', 'watch it on the live screen', 'soft', true),
];

export function AskFlow() {
  return (
    <Diagram
      title="Ask TalNex"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="Answers come from the saved proof, never from guessing. A suggested action is a button, so a paid run only starts when a person presses it. A custom test runs with the same safety rules and limits as any live test and never changes a score."
    />
  );
}
