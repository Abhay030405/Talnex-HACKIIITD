import { createOpenAPI } from 'fumadocs-openapi/server';

/** The Go API's reference. The spec lives with the API; a Go test keeps it in step with server.go. */
export const openapi = createOpenAPI({
  input: ['./content/openapi.yaml'],
  // the playground sends requests through this site, so the API needs no CORS change for it
  proxyUrl: '/api/docs/proxy',
});
