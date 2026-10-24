'use client';
import { box, Diagram, link } from './diagram';

const nodes = [
  box('hist', 0, 0, 'Public contest history', 'GraphQL · no login'),
  box('pick', 260, 0, 'Pick contests', 'last 5 + rating jumps ≥ +100 · skip < 7 days'),
  box('replay', 520, 0, 'Read each replay', 'userContestReplayEvents · every editor event'),
  box('paste', 780, 0, 'Find pastes', 'event 10 · size · time · quiet before · edits after', 'accent'),
  box('judge', 780, 160, 'Judge each paste', 'short or early = template · one go = Medium', 'question'),
  box('near', 520, 160, 'Same code nearby?', 'ranking pages around them · public final code · fingerprint', 'accent'),
  box('strong', 260, 160, 'Strong?', '2+ nearby share ≥90% · or Medium in 3+ contests', 'danger'),
  box('save', 0, 160, 'Signals + saved replay', 'hints beside the score · never a verdict', 'safe'),
];

const edges = [
  link('hist', 'r', 'pick', 'l'),
  link('pick', 'r', 'replay', 'l'),
  link('replay', 'r', 'paste', 'l'),
  link('paste', 'b', 'judge', 't'),
  link('judge', 'l', 'near', 'r', 'Medium, 12+ lines'),
  link('near', 'l', 'strong', 'r'),
  link('strong', 'l', 'save', 'r'),
];

export function LeetcodeFlow() {
  return (
    <Diagram
      title="LeetCode replay paste check"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="Many honest coders write in their own editor and paste, so one Medium paste is never raised on its own. Nothing about other contestants is kept: only how many matched and how closely."
    />
  );
}
