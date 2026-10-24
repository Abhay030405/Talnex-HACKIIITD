// Writes one MDX page per API endpoint, grouped by tag, from backend/api/openapi.yaml into
// content/docs/api-reference/<tag>/. Runs before every dev and build, so the pages always follow the spec;
// the generated folders are not committed. The hand-written index.mdx and meta.json there are kept.
import { rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

import { generateFiles } from 'fumadocs-openapi';
import { createOpenAPI } from 'fumadocs-openapi/server';

const OUT = './content/docs/api-reference';
const TAG_FOLDERS = ['account', 'events', 'projects', 'proof', 'candidates', 'walkthroughs', 'live', 'sms-gateway', 'health', 'dev'];

// clear old pages first, so an endpoint removed from the spec does not leave a page behind
await Promise.all(TAG_FOLDERS.map((dir) => rm(join(OUT, dir), { recursive: true, force: true })));

await generateFiles({
  input: createOpenAPI({ input: ['../../backend/api/openapi.yaml'] }),
  output: OUT,
  per: 'operation',
  groupBy: 'tag',
  includeDescription: true,
  meta: true,
});

// the generator also writes api-reference/meta.json; ours puts the intro page first and the tags in reading order
const meta = {
  title: 'API reference',
  pages: ['index', 'account', 'events', 'projects', 'proof', 'candidates', 'walkthroughs', 'live', 'sms-gateway', 'health', 'dev'],
};
await writeFile(join(OUT, 'meta.json'), `${JSON.stringify(meta, null, 2)}\n`);

console.log('API reference pages written to', OUT);
