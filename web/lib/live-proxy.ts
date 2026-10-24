// Passes the Go API's live event stream to the browser. The browser only ever talks to the website: the website's
// server signs the short-lived token and opens the stream, so no key or token reaches the browser.
import "server-only";

import { liveApiPath, type LiveKind } from "@/lib/live";
import { signApiToken } from "@/lib/token";

export interface LiveCaller {
  email: string;
  name?: string | null;
  role?: string | null;
}

export interface LiveDeps {
  baseUrl: string;
  secret: string;
  fetch: typeof fetch;
}

export const STREAM_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
} as const;

const plain = (error: string, status: number) => Response.json({ error }, { status });

/**
 * Opens the stream for `kind`/`id` as `caller` and returns it to pass straight through, unbuffered, until the
 * browser goes away (`signal`). A refusal comes back as plain words with the API's status.
 */
export async function proxyLive(
  kind: LiveKind,
  id: string,
  caller: LiveCaller,
  signal: AbortSignal,
  deps: LiveDeps,
): Promise<Response> {
  const token = await signApiToken(deps.secret, caller.email, caller.name, caller.role);
  let upstream: Response;
  try {
    upstream = await deps.fetch(`${deps.baseUrl}${liveApiPath(kind, id)}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
      cache: "no-store",
      signal,
    });
  } catch {
    return plain("Cannot reach the TalNex server.", 503);
  }
  if (upstream.status === 404) return plain("Not found.", 404);
  if (upstream.status === 401) return plain("Please sign in again.", 401);
  if (upstream.status === 403) return plain("This is not yours to open.", 403);
  if (upstream.status === 503) return plain("The live view is off on this server.", 503);
  if (!upstream.ok || !upstream.body) return plain(`The live view could not start (error ${upstream.status}).`, 502);
  return new Response(upstream.body, { status: 200, headers: STREAM_HEADERS });
}
