import { docsSettings } from '@/lib/env';
import { openapi } from '@/lib/openapi';

// Forwards playground requests only to the API addresses in TALNEX_DOCS_API_ORIGINS. Cookies are never forwarded.
const proxy = openapi.createProxy({ allowedOrigins: docsSettings().apiOrigins });

export const dynamic = 'force-dynamic';
export const { GET, HEAD, PUT, POST, PATCH, DELETE } = proxy;
