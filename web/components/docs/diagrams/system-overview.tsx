'use client';
import { box, Diagram, link } from './diagram';

// Top: people and the website. Middle: the Go API and Postgres, the only meeting point. Bottom: the workers and what
// they reach out to.
const nodes = [
  box('user', 330, 0, 'Recruiter / Judge', 'browser'),
  box('web', 330, 120, 'Website', 'Next.js · forms · reports · live view · Ask TalNex', 'accent'),
  box('api', 330, 250, 'Go API', 'owner check on every route · starts pipelines'),
  box('pg', 330, 390, 'Postgres', 'facts + results + the jobs queue · live_events', 'accent'),
  box('goworker', 0, 540, 'Go worker', 'GitHub · Codeforces · auto-confirm · cleanup'),
  box('pyworker', 330, 540, 'Python AI workers ×N', 'claims · plans · live test · proof check · scores · Ask'),
  box('sandboxd', 660, 540, 'sandboxd (Go)', 'fresh VM per run · limits · reaper', 'safe'),
  box('llm', 0, 700, 'LLMs', 'OpenRouter or Azure · fixed roles'),
  box('browser', 250, 700, 'Remote browser', 'TinyFish → Browserless fallback'),
  box('files', 500, 700, 'File storage', 'R2 / RustFS · screenshots · replays'),
  box('sites', 750, 700, 'Live sites · repos', 'used like a real person'),
];

const edges = [
  link('user', 'b', 'web', 't', 'HTTPS'),
  link('web', 'b', 'api', 't', 'signed token', 'yes'),
  link('api', 'b', 'pg', 't', 'save + queue jobs'),
  link('pg', 'l', 'goworker', 't', 'Go jobs'),
  link('pg', 'b', 'pyworker', 't', 'Python jobs'),
  link('pyworker', 'r', 'sandboxd', 'l', 'build + run repo'),
  link('pyworker', 'b', 'llm', 't'),
  link('pyworker', 'b', 'browser', 't', 'CDP'),
  link('pyworker', 'b', 'files', 't'),
  link('browser', 'r', 'sites', 'l', '', 'soft'),
  link('pg', 'r', 'api', 'r', 'pg_notify live → SSE', 'soft', true),
];

export function SystemOverview() {
  return (
    <Diagram
      title="TalNex system overview"
      nodes={nodes}
      edges={edges}
      size="large"
      caption="Go owns the API and the schema; Python owns everything that needs a model or a browser. They never call each other: they meet only in the Postgres jobs table. Live events travel back on pg_notify and reach the website as a Server-Sent Events stream."
    />
  );
}
