'use client';
import { box, Diagram, link } from './diagram';

// Top row goes out to the right; the bottom row comes back to the left, where the work happens.
const nodes = [
  box('assistant', 0, 0, 'AI assistant', 'Claude Code · Claude Desktop · Gemini CLI'),
  box('mcp', 330, 0, 'TalNex MCP server', 'mcp/ · runs on your computer · stdio · 19 tools', 'accent'),
  box('api', 660, 0, 'Go API', ':8080 · checks the owner on every call'),
  box('pg', 660, 230, 'Postgres', 'jobs table · results · live_events'),
  box('worker', 330, 230, 'Python worker', 'claims · test plan · live test · proof check · scores'),
  box('site', 0, 230, "The team's live site", 'used like a real person, a screenshot per step'),
];

const edges = [
  link('assistant', 'r', 'mcp', 'l', 'tool call'),
  link('mcp', 'r', 'api', 'l', 'HTTP + signed token', 'yes'),
  link('api', 'b', 'pg', 't', 'saves it, queues the first job'),
  link('pg', 'l', 'worker', 'r', 'takes the next job'),
  link('worker', 'l', 'site', 'r', 'TinyFish agent'),
  link('worker', 'b', 'pg', 'b', 'results + live events', 'soft'),
  link('api', 't', 'mcp', 't', 'JSON answers · SSE live stream', 'soft', true),
  link('mcp', 't', 'assistant', 't', 'proof card · live digest', 'soft'),
];

export function RequestFlow() {
  return (
    <Diagram
      title="How a request flows"
      nodes={nodes}
      edges={edges}
      size="medium"
      caption="The MCP server only talks to the Go API, as one person. Go and Python never call each other: they share the jobs table. The live stream (dashed, moving) is read for up to 120 seconds and folded into a digest."
    />
  );
}
