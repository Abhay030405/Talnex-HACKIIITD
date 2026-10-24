import { AlertCircle, ArrowRight, BriefcaseBusiness, Trophy, type LucideIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AuthFrame } from "@/components/ui/AuthFrame";
import { redirectIfSignedIn } from "@/lib/session";
import { signInError } from "@/lib/signin";

export const metadata: Metadata = { title: "Sign in" };

const DOORS: { href: string; Icon: LucideIcon; title: string; text: string }[] = [
  {
    href: "/login/recruiter",
    Icon: BriefcaseBusiness,
    title: "I am a recruiter",
    text: "Turn a resume into a proof report: which projects really work.",
  },
  {
    href: "/login/organizer",
    Icon: Trophy,
    title: "I run a hackathon",
    text: "Check every submission before judging, with proof behind each score.",
  },
];

export default async function LoginChooserPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  await redirectIfSignedIn();
  const message = signInError((await searchParams).error);

  return (
    <AuthFrame back={{ href: "/", label: "Back to home" }}>
      <div className="auth__head">
        <h1 className="auth__title">Who are you?</h1>
        <p className="auth__lead">Pick the way in that matches your work. Each has its own workspace.</p>
      </div>

      {message && (
        <p className="auth__alert" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          {message}
        </p>
      )}

      <div className="doors">
        {DOORS.map((door) => (
          <Link key={door.href} href={door.href} className="door">
            <span className="door__icon">
              <door.Icon size={20} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <span className="door__text">
              <span className="door__title">{door.title}</span>
              <span className="door__sub">{door.text}</span>
            </span>
            <ArrowRight className="door__go" size={18} aria-hidden="true" />
          </Link>
        ))}
      </div>

      <p className="auth__fine">Each email belongs to one kind of account.</p>
    </AuthFrame>
  );
}
