// Writes one MDX page per API endpoint, grouped by tag, from backend/api/openapi.yaml into
// content/docs/api-reference/<tag>/. Runs before every dev and build, so the pages always follow the spec;
// the generated folders are not committed. The hand-written index.mdx and meta.json there are kept.
import { readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

import { generateFiles } from 'fumadocs-openapi';
import { createOpenAPI } from 'fumadocs-openapi/server';

const OUT = './content/docs/api-reference';
const TAG_FOLDERS = ['account', 'events', 'projects', 'proof', 'candidates', 'walkthroughs', 'live', 'sms-gateway', 'health', 'dev'];

// the generator overwrites api-reference/meta.json, so keep the committed one as it is on disk
const metaFile = join(OUT, 'meta.json');
const metaBefore = await readFile(metaFile, 'utf8').catch(() => null);

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
const wanted = `${JSON.stringify(meta, null, 2)}\n`;
// it is a committed file: put back its own bytes when nothing changed, so a build leaves git clean (CRLF checkouts too)
const same = metaBefore !== null && metaBefore.replace(/\r\n/g, '\n') === wanted;
await writeFile(metaFile, same ? metaBefore : wanted);

console.log('API reference pages written to', OUT);
