'use client';
import { box, Diagram, link } from './diagram';

const nodes = [
  box('plan', 0, 0, 'Test plan step', 'what to do · what should be seen'),
  box('look', 260, 0, 'Look', 'accessibility snapshot · picture only if needed'),
  box('human', 260, 150, 'Human check?', 'CAPTCHA → Browserless solves it, else blocked', 'question'),
  box('model', 520, 0, 'Model picks ONE action', 'click · fill · press · navigate · read_email'),
  box('safe', 780, 0, 'Plain-code safety check', 'no pay · no delete · no messaging · only seen links', 'safe'),
  box('do', 780, 150, 'Browser does it', 'TinyFish or Browserless over CDP'),
  box('record', 520, 150, 'Record the step', 'screenshot · network · console · leak scan', 'accent'),
  box('final', 0, 150, 'Final look → proof check', 'a 2nd model sees only the pictures', 'safe'),
];

const edges = [
  link('plan', 'r', 'look', 'l'),
  link('look', 'b', 'human', 't', '', 'soft'),
  link('look', 'r', 'model', 'l'),
  link('model', 'r', 'safe', 'l'),
  link('safe', 'b', 'do', 't', 'allowed'),
  link('do', 'l', 'record', 'r'),
  link('record', 't', 'look', 'b', 'look again', 'soft', true),
  link('record', 'l', 'final', 'r', 'step done → next step · plan done'),
];

export function AgentLoop() {
  return (
    <Diagram
      title="The live test loop"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="TalNex does not hand a whole task to a black-box agent. It loops one action at a time, checks each action in plain code before it runs, and saves proof after every step. Limits: 40 actions and 240 seconds per plan, 3 tries per claim; running out is 'blocked', never 'broken'."
    />
  );
}
