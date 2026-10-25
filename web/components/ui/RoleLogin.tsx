import { AlertCircle, KeyRound, Lock, Mail, User } from "lucide-react";
import { AuthError } from "next-auth";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signIn, signInOptions } from "@/auth";
import { AuthFrame } from "@/components/ui/AuthFrame";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { rememberDoor } from "@/lib/door";
import { redirectIfSignedIn } from "@/lib/session";
import { MAX_PASSWORD, MIN_PASSWORD, cleanEmail, passwordProblem, registerPassword, signInError } from "@/lib/signin";
import { homePath, type Role } from "@/lib/types";

const COPY: Record<Role, { title: string; register: string; text: string; other: Role }> = {
  recruiter: {
    title: "Recruiter sign‑in", // a hyphen that never breaks the title across lines
    register: "Create a recruiter account",
    text: "Turn a resume into a proof report: which projects really work and how they are built.",
    other: "organizer",
  },
  organizer: {
    title: "Organizer sign‑in", // a hyphen that never breaks the title across lines
    register: "Create an organizer account",
    text: "Check every submission before judging starts, with proof behind every score.",
    other: "recruiter",
  },
};

async function clientIp(): Promise<string> {
  const h = await headers();
  return (h.get("x-forwarded-for") ?? "").split(",")[0].trim() || h.get("x-real-ip") || "";
}

/** The sign-in (or sign-up) form for one door. The door is remembered first, so it survives the trip to Google and back. */
export async function RoleLogin({ role, error, mode }: { role: Role; error?: string; mode?: string }) {
  await redirectIfSignedIn();

  const options = signInOptions();
  const copy = COPY[role];
  const registering = mode === "register";
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
      await signIn("dev", { email: form.get("email"), redirectTo: homePath(role) });
    } catch (failure) {
      // A refused sign-in comes back here with the reason. Anything else, including Next's own redirect, goes on.
      if (failure instanceof AuthError) redirect(`/login/${role}?error=failed`);
      throw failure;
    }
  }

  async function withPassword(form: FormData) {
    "use server";
    await rememberDoor(role);
    try {
      await signIn("password", { email: form.get("email"), password: form.get("password"), redirectTo: homePath(role) });
    } catch (failure) {
      if (failure instanceof AuthError) redirect(`/login/${role}?error=wrong-password`);
      throw failure;
    }
  }

  async function register(form: FormData) {
    "use server";
    const email = cleanEmail(form.get("email"));
    const name = String(form.get("name") ?? "").trim().slice(0, 120);
    const password = String(form.get("password") ?? "");
    const back = `/login/${role}?mode=register&error=`;
    if (!email) redirect(`${back}bad-email`);
    const bad = passwordProblem(password, String(form.get("confirm") ?? ""));
    if (bad) redirect(`${back}${bad.includes("match") ? "no-match" : "bad-password"}`);
    try {
      await registerPassword({ email, name }, role, password, await clientIp());
    } catch (failure) {
      if (failure instanceof ApiError) {
        redirect(`${back}${failure.status === 409 ? "taken" : failure.status === 403 ? "wrong-door" : failure.status === 429 ? "slow-down" : "failed"}`);
      }
      throw failure;
    }
    await rememberDoor(role);
    try {
      await signIn("password", { email, password, redirectTo: homePath(role) });
    } catch (failure) {
      if (failure instanceof AuthError) redirect(`/login/${role}?error=wrong-password`);
      throw failure;
    }
  }

  return (
    <AuthFrame back={{ href: "/login", label: "Choose another way in" }}>
      <div className="auth__head">
        <h1 className="auth__title">{registering ? copy.register : copy.title}</h1>
        <p className="auth__lead">{copy.text}</p>
      </div>

      {message && (
        <p className="auth__alert" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          {message}
        </p>
      )}

      {options.google && !registering && (
        <form action={withGoogle}>
          <Button variant="secondary" size="lg" block>
            Continue with Google
          </Button>
        </form>
      )}

      {options.google && !registering && <div className="auth__or">or</div>}

      <form className="auth__form" action={registering ? register : withPassword}>
        {registering && (
          <div className="auth__field">
            <label className="auth__label" htmlFor="name">
              Your name
            </label>
            <div className="auth__input-wrap">
              <User size={16} aria-hidden="true" />
              <input className="auth__input" id="name" name="name" autoComplete="name" maxLength={120} placeholder="Asha Rao" />
            </div>
          </div>
        )}
        <div className="auth__field">
          <label className="auth__label" htmlFor="pw-email">
            Email
          </label>
          <div className="auth__input-wrap">
            <Mail size={16} aria-hidden="true" />
            <input className="auth__input" id="pw-email" name="email" type="email" autoComplete="email" required placeholder="you@example.com" />
          </div>
        </div>
        <div className="auth__field">
          <label className="auth__label" htmlFor="password">
            Password
          </label>
          <div className="auth__input-wrap">
            <KeyRound size={16} aria-hidden="true" />
            <input
              className="auth__input"
              id="password"
              name="password"
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              required
              minLength={registering ? MIN_PASSWORD : undefined}
              maxLength={MAX_PASSWORD}
              aria-describedby={registering ? "password-hint" : undefined}
            />
          </div>
          {registering && (
            <span className="auth__hint" id="password-hint">
              {MIN_PASSWORD} to {MAX_PASSWORD} characters.
            </span>
          )}
        </div>
        {registering && (
          <div className="auth__field">
            <label className="auth__label" htmlFor="confirm">
              Password again
            </label>
            <div className="auth__input-wrap">
              <KeyRound size={16} aria-hidden="true" />
              <input className="auth__input" id="confirm" name="confirm" type="password" autoComplete="new-password" required maxLength={MAX_PASSWORD} />
            </div>
          </div>
        )}
        <Button variant="primary" size="lg" block>
          {registering ? "Create account" : "Sign in"}
        </Button>
      </form>

      <p className="auth__switch">
        {registering ? (
          <>
            Have an account? <Link href={`/login/${role}`}>Sign in</Link>
          </>
        ) : (
          <>
            New here? <Link href={`/login/${role}?mode=register`}>Create an account</Link>
          </>
        )}
      </p>

      {options.dev && !registering && (
        <>
          <div className="auth__or">or</div>
          <form className="auth__form" action={withEmail}>
            <div className="auth__field">
              <label className="auth__label" htmlFor="email">
                Email only (local testing)
              </label>
              <div className="auth__input-wrap">
                <Mail size={16} aria-hidden="true" />
                <input className="auth__input" id="email" name="email" type="email" autoComplete="email" required placeholder="you@example.com" />
              </div>
              <span className="auth__hint">Email-only sign-in is for local testing. It is off in production.</span>
            </div>
            <Button variant="secondary" size="lg" block>
              Sign in without a password
            </Button>
          </form>
        </>
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
