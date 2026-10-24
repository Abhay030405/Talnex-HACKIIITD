import type { Metadata } from "next";
import Link from "next/link";

import { BackIcon } from "@/components/ui/Icons";

export const metadata: Metadata = { title: "Page not found" };

// Shown for any address the site doesn't have, and for an event, project or candidate that isn't yours
// (the API answers "not found" to strangers, so nobody can tell whether someone else's results exist).
export default function NotFound() {
  return (
    <div className="login">
      <div className="login__doors stack">
        <div className="page-header page-header--center">
          <span className="login__tag">404</span>
          <h1 className="page-header__title">This page isn&apos;t here</h1>
          <p className="page-header__lead">
            The link may be old or mistyped, or it points to results that belong to another account. Results are
            private to the person who started the check.
          </p>
        </div>
        {/* "/" sends a signed-in person to their own workspace and everyone else to the start page. */}
        <div className="not-found__actions">
          <Link href="/" className="button button--primary">
            <BackIcon />
            Go to the start
          </Link>
        </div>
      </div>
    </div>
  );
}
