// The sign-in door a person walked through, recruiter or organizer. It is kept for a few minutes in a cookie so
// it survives the trip to Google and back; then sign-in puts it in the session and the API token carries it.
import "server-only";

import { cookies } from "next/headers";

import { env } from "@/lib/env";
import { isRole, type Role } from "@/lib/types";

export const DOOR_COOKIE = "talnex_door";
/** Long enough to finish signing in with Google, short enough not to linger. */
export const DOOR_SECONDS = 600;

export async function rememberDoor(role: Role): Promise<void> {
  (await cookies()).set(DOOR_COOKIE, role, {
    httpOnly: true,
    sameSite: "lax",
    secure: env.secureCookies,
    path: "/",
    maxAge: DOOR_SECONDS,
  });
}

export async function recallDoor(): Promise<Role | undefined> {
  const value = (await cookies()).get(DOOR_COOKIE)?.value;
  return isRole(value) ? value : undefined;
}

export async function forgetDoor(): Promise<void> {
  (await cookies()).delete(DOOR_COOKIE);
}
