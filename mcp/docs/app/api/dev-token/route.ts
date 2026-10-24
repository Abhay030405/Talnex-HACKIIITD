// "Get a test token" for the API playground. Local testing only: it exists only with TALNEX_DOCS_DEV_TOKENS=true,
// answers only on this computer, and signs exactly like web/lib/token.ts. AUTH_SECRET never leaves the server, and the
// token is never logged.
import { SignJWT } from 'jose';

import { docsSettings } from '@/lib/env';

export const dynamic = 'force-dynamic';

const ROLES = new Set(['organizer', 'recruiter']);
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const json = (status: number, body: unknown) =>
  Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });

function refusal(request: Request): Response | null {
  const settings = docsSettings();
  if (!settings.devTokens) {
    return json(404, { error: 'Test tokens are off. Start the docs site with TALNEX_DOCS_DEV_TOKENS=true to use them.' });
  }
  if (!LOCAL_HOSTS.has(new URL(request.url).hostname)) {
    return json(403, { error: 'Test tokens are only given on this computer (localhost).' });
  }
  if (!settings.authSecret) {
    return json(503, { error: 'AUTH_SECRET is not set for the docs site (it reads the repository .env).' });
  }
  return null;
}

/** Whether the helper is on, so the page can say so. */
export function GET(request: Request) {
  const refused = refusal(request);
  return json(200, { enabled: !refused, minutes: docsSettings().devTokenMinutes,
                     reason: refused ? 'off' : undefined });
}

export async function POST(request: Request) {
  const refused = refusal(request);
  if (refused) return refused;
  let body: { email?: unknown; role?: unknown };
  try {
    body = await request.json();
  } catch {
    return json(400, { error: 'Send JSON with an email and a role.' });
  }
  const email = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
  const role = typeof body.role === 'string' ? body.role : '';
  if (!EMAIL.test(email)) return json(400, { error: 'Type a valid email.' });
  if (!ROLES.has(role)) return json(400, { error: 'The role must be organizer or recruiter.' });

  const { authSecret, devTokenMinutes } = docsSettings();
  const now = Math.floor(Date.now() / 1000);
  const exp = now + devTokenMinutes * 60;
  const token = await new SignJWT({ email, name: '', role })
    .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
    .setIssuedAt(now)
    .setExpirationTime(exp)
    .sign(new TextEncoder().encode(authSecret));
  return json(200, { token, email, role, expires_at: new Date(exp * 1000).toISOString() });
}
