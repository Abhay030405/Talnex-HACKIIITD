// Page guards: who may see a page. A signed-out person goes to the right sign-in door; a person with the other
// role goes back to their own workspace.
import "server-only";

import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { homePath, type Role } from "@/lib/types";

export async function requireRole(role: Role) {
  const session = await auth();
  if (!session?.user?.email) redirect(`/login/${role}`);
  const own = session.user.role;
  if (own !== role) redirect(own ? homePath(own) : "/login");
  return session;
}

/** Sends a signed-in person with a role straight to their workspace. For the public pages. */
export async function redirectIfSignedIn() {
  const role = (await auth())?.user?.role;
  if (role) redirect(homePath(role));
}
