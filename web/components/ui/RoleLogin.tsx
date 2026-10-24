import { AlertCircle, Lock, Mail } from "lucide-react";
import { AuthError } from "next-auth";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signIn, signInOptions } from "@/auth";
import { AuthFrame } from "@/components/ui/AuthFrame";
import { Button } from "@/components/ui/Button";
import { rememberDoor } from "@/lib/door";
import { redirectIfSignedIn } from "@/lib/session";
import { signInError } from "@/lib/signin";
import { homePath, type Role } from "@/lib/types";

const COPY: Record<Role, { title: string; text: string; other: Role }> = {
  recruiter: {
    title: "Recruiter sign‑in", // a hyphen that never breaks the title across lines
    text: "Turn a resume into a proof report: which projects really work and how they are built.",
    other: "organizer",
  },
  organizer: {
    title: "Organizer sign‑in", // a hyphen that never breaks the title across lines
    text: "Check every submission before judging starts, with proof behind every score.",
    other: "recruiter",
  },
};

/** The sign-in form for one door. The door is remembered first, so it survives the trip to Google and back. */
export async function RoleLogin({ role, error }: { role: Role; error?: string }) {
  await redirectIfSignedIn();

  const options = signInOptions();
  const copy = COPY[role];
  const message = signInError(error, role);

  async function withGoogle() {
    "use server";
    await rememberDoor(role);
    await signIn("google", { redirectTo: homePath(role) });
  }

  async function withEmail(form: FormData) {
    "use server";
    await rememberDoor(role);
    try {
      await signIn("dev", {
        email: form.get("email"),
        redirectTo: homePath(role),
      });
    } catch (failure) {
      // A refused sign-in comes back here with the reason. Anything else, including Next's own redirect, goes on.
      if (failure instanceof AuthError) redirect(`/login/${role}?error=failed`);
      throw failure;
    }
  }

  return (
    <AuthFrame back={{ href: "/login", label: "Choose another way in" }}>
      <div className="auth__head">
        <h1 className="auth__title">{copy.title}</h1>
        <p className="auth__lead">{copy.text}</p>
      </div>

      {message && (
        <p className="auth__alert" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          {message}
        </p>
      )}

      {options.google && (
        <form action={withGoogle}>
          <Button variant="secondary" size="lg" block>
            Continue with Google
          </Button>
        </form>
      )}

      {options.google && options.dev && <div className="auth__or">or</div>}

      {options.dev && (
        <form className="auth__form" action={withEmail}>
          <div className="auth__field">
            <label className="auth__label" htmlFor="email">
              Email
            </label>
            <div className="auth__input-wrap">
              <Mail size={16} aria-hidden="true" />
              <input
                className="auth__input"
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
              />
            </div>
            <span className="auth__hint">Email-only sign-in is for local testing. It is off in production.</span>
          </div>
          <Button variant="primary" size="lg" block>
            Sign in
          </Button>
        </form>
      )}

      {!options.google && !options.dev && (
        <p className="notice">
          No way to sign in is switched on. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or ENABLE_DEV_LOGIN=true for
          local work, then restart the website.
        </p>
      )}

      <p className="auth__fine">
        <Lock size={14} aria-hidden="true" />
        Each email belongs to one kind of account. Your results are private to you.
      </p>

      <p className="auth__switch">
        Wrong sign-in? <Link href={`/login/${copy.other}`}>Use the {copy.other} sign-in</Link>
      </p>
    </AuthFrame>
  );
}
