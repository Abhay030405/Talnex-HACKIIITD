'use client';
import { box, Diagram, link } from './diagram';

// Left to right along the top, then back along the bottom to the proof card.
const nodes = [
  box('precheck', 0, 0, '1 · Precheck', 'do the live link, repo and video open?'),
  box('claims', 290, 0, '2 · Claims', 'from the video, the criteria or the resume'),
  box('plan', 580, 0, '3 · Test plan', 'steps and the expected result for each claim'),
  box('live', 870, 0, '4 · Live test', 'the agent uses the site, a screenshot per step'),
  box('proof', 870, 220, '5 · Proof check', 'an independent second check, then the never-blame ladder'),
  box('score', 580, 220, '6 · Scoring', 'a score out of 10 per feature, the TalNex score'),
  box('card', 290, 220, '7 · Proof card', 'what works, how sure, and why', 'accent'),
  box('gap', 1160, 110, 'Could not test', 'left out of the score, reason shown, never "fake"', 'safe'),
];

const edges = [
  link('precheck', 'r', 'claims', 'l', 'links open'),
  link('claims', 'r', 'plan', 'l', 'testable claims'),
  link('plan', 'r', 'live', 'l', 'a plan per claim'),
  link('live', 'b', 'proof', 't', 'screenshots + steps'),
  link('proof', 'l', 'score', 'r', 'confirmed verdicts'),
  link('score', 'l', 'card', 'r', 'flags beside, never subtracted', 'yes'),
  link('live', 'r', 'gap', 't', 'site down, login wall', 'soft'),
  link('proof', 'r', 'gap', 'b', 'not confirmed', 'soft'),
];

export function CheckPipeline() {
  return (
    <Diagram
      title="The check pipeline"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="Each stage is its own job, so a failure retries only that stage. watch_live shows these stages as they start and finish. The AI opinion on the card is labelled as opinion and is never part of the score."
    />
  );
}
