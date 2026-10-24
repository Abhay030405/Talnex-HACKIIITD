import { env } from "@/lib/env";
import { openapi } from "@/lib/docs/openapi";

// The docs API playground sends every request here (?url=<api address>). An address in TALNEX_DOCS_API_ORIGINS (what
// a browser calls the API, e.g. http://localhost:8080) is sent on to API_BASE_URL (what this server calls it, e.g.
// http://api:8080 inside Docker). Anything else is refused. Cookies are never forwarded.
export const dynamic = "force-dynamic";

function toApi(request: Request): Request | null {
  const url = new URL(request.url);
  const target = url.searchParams.get("url");
  if (!target) return null;
  let parsed: URL;
  try {
    parsed = new URL(target);
  } catch {
    return null;
  }
  if (!env.docsApiOrigins.includes(parsed.origin)) return null;
  url.searchParams.set("url", env.apiBaseUrl + parsed.pathname + parsed.search);
  return new Request(url, request);
}

async function handle(request: Request): Promise<Response> {
  const forwarded = toApi(request);
  if (!forwarded) return Response.json({ error: "That address is not the TalNex API." }, { status: 403 });
  const proxy = openapi.createProxy({ allowedOrigins: [new URL(env.apiBaseUrl).origin] });
  return proxy.handle(forwarded);
}

export { handle as GET, handle as HEAD, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
