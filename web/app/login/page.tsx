import type { Metadata } from "next";
import Link from "next/link";

import { ArrowIcon, BackIcon, BriefcaseIcon, TrophyIcon } from "@/components/ui/Icons";
import { redirectIfSignedIn } from "@/lib/session";
import { signInError } from "@/lib/signin";

export const metadata: Metadata = { title: "Sign in" };

const DOORS = [
  {
    href: "/login/recruiter",
    icon: <BriefcaseIcon />,
    title: "I am a recruiter",
    text: "Turn a resume into a proof report: which projects really work and how they are built.",
    go: "Recruiter sign-in",
  },
  {
    href: "/login/organizer",
    icon: <TrophyIcon />,
    title: "I run a hackathon",
    text: "Check every submission before judging, with a score per feature and the proof behind it.",
    go: "Organizer sign-in",
  },
];

export default async function LoginChooserPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  await redirectIfSignedIn();
  const message = signInError((await searchParams).error);

  return (
    <div className="login">
      <Link href="/" className="back-link login__back">
        <BackIcon />
        Back to home
      </Link>

      <div className="login__doors stack">
        <div className="page-header page-header--center">
          <span className="login__tag">Secure access</span>
          <h1 className="page-header__title">Who are you?</h1>
          <p className="page-header__lead">Pick the way in that matches your work. Each has its own workspace.</p>
        </div>

        {message && (
          <p className="form-error" role="alert">
            {message}
          </p>
        )}

        <div className="grid grid--2">
          {DOORS.map((door) => (
            <Link key={door.href} href={door.href} className="card card--soft card--link">
              <div className="card__icon">{door.icon}</div>
              <h2 className="card__title">{door.title}</h2>
              <p className="card__text">{door.text}</p>
              <span className="card__go">
                {door.go} <ArrowIcon size={16} />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
