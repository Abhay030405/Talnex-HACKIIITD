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
    default:
      return "We could not sign you in. Please try again.";
  }
}
