import { AuthError } from "next-auth";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signIn, signInOptions } from "@/auth";
import { ArrowIcon, BackIcon, BriefcaseIcon, TrophyIcon } from "@/components/ui/Icons";
import { rememberDoor } from "@/lib/door";
import { redirectIfSignedIn } from "@/lib/session";
import { signInError } from "@/lib/signin";
import { homePath, type Role } from "@/lib/types";

const COPY: Record<Role, { tag: string; title: string; text: string; other: Role }> = {
  recruiter: {
    tag: "Recruiter access",
    title: "Recruiter sign‑in", // a hyphen that never breaks the title across lines
    text: "Turn a resume into a proof report: which projects really work and how they are built.",
    other: "organizer",
  },
  organizer: {
    tag: "Organizer access",
    title: "Organizer sign‑in", // a hyphen that never breaks the title across lines
    text: "Check every submission before judging starts, with proof behind every score.",
    other: "recruiter",
  },
};

/** The sign-in card for one door. The door is remembered first, so it survives the trip to Google and back. */
export async function RoleLogin({ role, error }: { role: Role; error?: string }) {
  await redirectIfSignedIn();

  const options = signInOptions();
  const copy = COPY[role];
  const Icon = role === "recruiter" ? BriefcaseIcon : TrophyIcon;
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

  return (
    <div className="login">
      <Link href="/login" className="back-link login__back">
        <BackIcon />
        Choose another way in
      </Link>

      <div className="login__wrap">
        <div className="login__card">
          <div className="login__head">
            <div className="login__mark">
              <Icon size={26} />
            </div>
            <div>
              <span className="login__tag">{copy.tag}</span>
              <h1 className="login__title">{copy.title}</h1>
            </div>
          </div>

          <p className="login__sub">{copy.text}</p>

          {message && (
            <p className="form-error" role="alert">
              {message}
            </p>
          )}

          <div className="login__body">
            {options.google && (
              <form action={withGoogle}>
                <button type="submit" className="button button--primary button--lg button--block">
                  Continue with Google <ArrowIcon size={16} />
                </button>
              </form>
            )}

            {options.google && options.dev && <div className="divider">or</div>}

            {options.dev && (
              <form className="form" action={withEmail}>
                <div className="field">
                  <label className="field__label" htmlFor="email">
                    Email
                  </label>
                  <input
                    className="input"
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    placeholder="you@example.com"
                  />
                  <span className="field__hint">Email-only sign-in is for local testing. It is off in production.</span>
                </div>
                <button type="submit" className="button button--soft button--lg button--block">
                  Sign in <ArrowIcon size={16} />
                </button>
              </form>
            )}

            {!options.google && !options.dev && (
              <p className="notice">
                No way to sign in is switched on. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or ENABLE_DEV_LOGIN=true
                for local work, then restart the website.
              </p>
            )}
          </div>

          <p className="login__fine">Each email belongs to one kind of account. Your results are private to you.</p>
        </div>

        <Link href={`/login/${copy.other}`} className="meta">
          Wrong sign-in? Use the {copy.other} sign-in
        </Link>
      </div>
    </div>
  );
}
