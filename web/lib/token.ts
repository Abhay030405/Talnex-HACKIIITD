// The short-lived token that tells the Go API who is calling. The API checks it in backend/internal/auth/auth.go:
// HS256 with AUTH_SECRET, an email, an optional name, an optional role (recruiter or organizer), and an expiry,
// which the API requires. Free of server-only imports so it can be tested.
import { SignJWT } from "jose";

import { isRole } from "@/lib/types";

/** Long enough for one call to the API, short enough to be useless if it ever leaked. */
export const API_TOKEN_SECONDS = 120;

export async function signApiToken(
  secret: string,
  email: string,
  name?: string | null,
  role?: string | null,
  seconds: number = API_TOKEN_SECONDS,
): Promise<string> {
  const cleanEmail = email.trim().toLowerCase();
  if (!cleanEmail) throw new Error("An API token needs the person's email");
  if (role && !isRole(role)) throw new Error(`Unknown role "${role}"`);
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ email: cleanEmail, name: name?.trim() ?? "", ...(role ? { role } : {}) })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuedAt(now)
    .setExpirationTime(now + seconds)
    .sign(new TextEncoder().encode(secret));
}
