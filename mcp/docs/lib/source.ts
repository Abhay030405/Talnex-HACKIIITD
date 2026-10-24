import { loader } from 'fumadocs-core/source';
import { metaSchema, pageSchema } from 'fumadocs-core/source/schema';
import { defineDocs } from 'fumadocs-mdx/macro';
import { openapiPlugin } from 'fumadocs-openapi/server';

import { docsRoute } from './shared';

const docs = defineDocs({
  dir: 'content/docs',
  docs: { schema: pageSchema },
  meta: { schema: metaSchema },
});

export const source = loader({
  baseUrl: docsRoute,
  source: docs.toFumadocsSource(),
  // a method badge (GET, POST...) beside each API reference page in the sidebar
  plugins: [openapiPlugin()],
});
