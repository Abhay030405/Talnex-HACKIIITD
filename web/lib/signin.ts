// Sign-in decisions, kept apart from Auth.js so they can be tested.
import { ApiError, callApi, type ApiDeps } from "@/lib/api";
import { ROLE_NAMES, type Role } from "@/lib/types";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** A usable email for the local email-only sign-in, cleaned the way the API stores it, or null. */
export function cleanEmail(value: unknown): string | null {
  const email = String(value ?? "")
    .trim()
    .toLowerCase();
  return EMAIL.test(email) && email.length <= 254 ? email : null;
}

export type DoorCheck = "ok" | "wrong-door" | "no-door";

/**
 * Asks the API whether this person may use this door. The API sets an account's role at its first sign-in and
 * refuses the other role afterwards (403). If the API cannot be reached the person is let in, and their
 * workspace shows the problem instead of the sign-in page failing for an unclear reason.
 */
export async function checkDoor(
  person: { email: string; name?: string | null },
  door: Role | undefined,
  deps?: ApiDeps,
): Promise<DoorCheck> {
  if (!door) return "no-door";
  try {
    await callApi({ ...person, role: door }, "/v1/me", {}, deps);
    return "ok";
  } catch (e) {
    return e instanceof ApiError && e.status === 403 ? "wrong-door" : "ok";
  }
}

/** Errors a sign-in page can show: ours, and the codes Auth.js adds to the address. */
export function signInError(code: string | undefined, role?: Role): string | null {
  if (!code) return null;
  const other: Role | undefined = role === "recruiter" ? "organizer" : role === "organizer" ? "recruiter" : undefined;
  switch (code) {
    case "wrong-door":
      return other
        ? `This email already has a ${ROLE_NAMES[other].toLowerCase()} account. Use the ${other} sign-in instead.`
        : "This email already has a different kind of account.";
    case "no-door":
      return "Signing in took too long. Choose your way in again.";
    case "unverified":
      return "That Google account has no verified email address.";
    case "AccessDenied":
      return "Sign-in was cancelled or refused.";
    case "Configuration":
      return "Sign-in is not set up correctly on this server. Tell the TalNex team.";
    case "CredentialsSignin":
    case "wrong-password":
      return "That email and password do not match, or there were too many tries. Wait a few minutes if so.";
    case "bad-email":
      return "Type a valid email address.";
    case "bad-password":
      return `Use a password of ${MIN_PASSWORD} to ${MAX_PASSWORD} characters.`;
    case "no-match":
      return "The two passwords do not match.";
    case "taken":
      return "This email already has an account. Sign in instead.";
    case "slow-down":
      return "Too many tries. Wait a few minutes and try again.";
    default:
      return "We could not sign you in. Please try again.";
  }
}

// ---------- Email and password ----------

export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 128;

/** What is wrong with a new password, in words, or null. The same rule as the API (backend/internal/http/password.go). */
export function passwordProblem(password: string, confirm?: string): string | null {
  const length = [...password].length;
  if (length < MIN_PASSWORD || length > MAX_PASSWORD) {
    return `Use a password of ${MIN_PASSWORD} to ${MAX_PASSWORD} characters.`;
  }
  if (confirm !== undefined && confirm !== password) return "The two passwords do not match.";
  return null;
}

/** The visitor's address as the website sees it, sent to the API for its sign-in rate limit. */
export const CLIENT_IP_HEADER = "X-Talnex-Client-Ip";

const ipHeaders = (clientIp: string): Record<string, string> =>
  clientIp ? { [CLIENT_IP_HEADER]: clientIp.slice(0, 64) } : {};

/** Checks an email and password with the API: the account, or null when they are wrong (or after too many tries). */
export async function checkPassword(
  email: string,
  password: string,
  clientIp: string,
  deps?: ApiDeps,
): Promise<{ email: string; name: string; role: string } | null> {
  try {
    return await callApi(
      { email },
      "/v1/auth/password-login",
      { method: "POST", body: { password }, headers: ipHeaders(clientIp) },
      deps,
    );
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 429)) return null;
    throw e;
  }
}

/** Creates an email and password account through one door. Throws ApiError with words to show when refused. */
export async function registerPassword(
  person: { email: string; name: string },
  door: Role,
  password: string,
  clientIp: string,
  deps?: ApiDeps,
): Promise<void> {
  await callApi(
    { ...person, role: door },
    "/v1/auth/register",
    { method: "POST", body: { password }, headers: ipHeaders(clientIp) },
    deps,
  );
}
