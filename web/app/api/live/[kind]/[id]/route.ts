// The live view's stream. The browser opens this route; the website's server checks who is signed in, opens the Go
// API's stream with a signed token and passes it straight through. The browser never holds a key.
import { auth } from "@/auth";
import { env } from "@/lib/env";
import { isLiveKind } from "@/lib/live";
import { proxyLive } from "@/lib/live-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ kind: string; id: string }> }) {
  const { kind, id } = await params;
  if (!isLiveKind(kind) || !id) return Response.json({ error: "Unknown live view." }, { status: 400 });
  const user = (await auth())?.user;
  if (!user?.email) return Response.json({ error: "Please sign in." }, { status: 401 });
  return proxyLive(kind, id, { email: user.email, name: user.name, role: user.role }, request.signal, {
    baseUrl: env.apiBaseUrl,
    secret: env.authSecret,
    fetch,
  });
}
