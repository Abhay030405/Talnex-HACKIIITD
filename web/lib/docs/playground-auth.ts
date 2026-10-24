// The API playground (fumadocs-openapi) keeps its Authorization field in sessionStorage under
// `<storageKeyPrefix>auth-<securityScheme>` and reads it when a playground mounts. Writing a "Bearer <token>" there
// fills the field for every API page in this tab. The token is the signed-in person's own short-lived API token.

const AUTH_KEY = "fumadocs-openapi-auth-bearerAuth"; // default prefix + the spec's `bearerAuth` scheme
const EXPIRY_KEY = "talnex-docs-session-expires";
const REFRESH_EARLY_MS = 60_000;

export interface SessionTokenAnswer {
  token: string;
  expires_at: string;
  email: string;
  role: string;
}

export function storeSessionToken(answer: SessionTokenAnswer): void {
  try {
    sessionStorage.setItem(AUTH_KEY, JSON.stringify(`Bearer ${answer.token}`));
    sessionStorage.setItem(EXPIRY_KEY, answer.expires_at);
  } catch {
    // Storage blocked (private mode): the button still shows the token to paste.
  }
}

/** True when a stored session token is still good for at least a minute. */
export function hasFreshSessionToken(now = Date.now()): boolean {
  try {
    const expires = Date.parse(sessionStorage.getItem(EXPIRY_KEY) ?? "");
    return Number.isFinite(expires) && expires - now > REFRESH_EARLY_MS;
  } catch {
    return false;
  }
}

/** Asks the website for the signed-in person's token; null when nobody is signed in. */
export async function fetchSessionToken(): Promise<SessionTokenAnswer | null> {
  const r = await fetch("/api/docs/session-token", { method: "POST" });
  if (!r.ok) return null;
  return (await r.json()) as SessionTokenAnswer;
}
