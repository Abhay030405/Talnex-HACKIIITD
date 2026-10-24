// "Use my session" for the API playground: a short-lived API token for whoever is signed in, so the docs can call the
// API as them. Only for a signed-in person; the token names their own email and role, and is never logged.
import { auth } from "@/auth";
import { env } from "@/lib/env";
import { signApiToken } from "@/lib/token";

export const dynamic = "force-dynamic";

const json = (status: number, body: unknown) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });

export async function POST() {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return json(401, { error: "Sign in to use your own session." });
  const minutes = env.docsSessionTokenMinutes;
  const token = await signApiToken(env.authSecret, email, session.user.name, session.user.role, minutes * 60);
  return json(200, {
    token,
    email,
    role: session.user.role ?? "",
    expires_at: new Date(Date.now() + minutes * 60_000).toISOString(),
  });
}
