// Sign-in (Auth.js): Google, plus an email-only way in for local work. The session is a signed cookie; the
// person's role is the door they first came through, confirmed by the API.
import NextAuth, { type DefaultSession } from "next-auth";
import type { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

import { forgetDoor, recallDoor } from "@/lib/door";
import { env } from "@/lib/env";
import { checkDoor, cleanEmail } from "@/lib/signin";
import { isRole, type Role } from "@/lib/types";

declare module "next-auth" {
  interface Session {
    user: { role?: Role } & DefaultSession["user"];
  }
}

/** A week: long enough not to annoy, short enough that a forgotten laptop does not stay signed in for a month. */
const SESSION_SECONDS = 7 * 24 * 60 * 60;

function providers(): Provider[] {
  const list: Provider[] = [];
  if (env.googleClientId && env.googleClientSecret) {
    list.push(Google({ clientId: env.googleClientId, clientSecret: env.googleClientSecret }));
  }
  if (env.devLogin) {
    list.push(
      Credentials({
        id: "dev",
        name: "Email (local)",
        credentials: { email: { label: "Email", type: "email" } },
        authorize(credentials) {
          const email = cleanEmail(credentials?.email);
          return email ? { id: email, email, name: email.split("@")[0] } : null;
        },
      }),
    );
  }
  return list;
}

export const { handlers, auth, signIn, signOut } = NextAuth(() => ({
  providers: providers(),
  session: { strategy: "jwt", maxAge: SESSION_SECONDS },
  pages: { signIn: "/login", error: "/login" },
  trustHost: true,
  secret: env.authSecret,
  callbacks: {
    // A string sends the person back to that page with the reason instead of signing them in.
    async signIn({ user, account, profile }) {
      if (account?.provider === "google" && profile?.email_verified !== true) return "/login?error=unverified";
      const door = await recallDoor();
      if (!user.email) return door ? `/login/${door}?error=failed` : "/login?error=failed";
      const check = await checkDoor({ email: user.email, name: user.name }, door);
      if (check === "no-door") return "/login?error=no-door";
      if (check === "wrong-door") return `/login/${door}?error=wrong-door`;
      return true;
    },
    // At sign-in the role is the door the person came through; afterwards it stays as it was.
    async jwt({ token, user }) {
      if (user) {
        token.role = await recallDoor();
        await forgetDoor();
      }
      return token;
    },
    session({ session, token }) {
      session.user.role = isRole(token.role) ? token.role : undefined;
      return session;
    },
  },
}));

/** Which sign-in ways are switched on, for the sign-in page. */
export function signInOptions() {
  return { google: Boolean(env.googleClientId && env.googleClientSecret), dev: env.devLogin };
}
