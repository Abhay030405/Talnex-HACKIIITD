import Link from "next/link";

import { auth, signOut } from "@/auth";

/** The top bar on public pages. The signed-in workspace has its own navigation. */
export async function Nav() {
  const signedIn = Boolean((await auth())?.user);

  async function leave() {
    "use server";
    await signOut({ redirectTo: "/" });
  }

  return (
    <header className="nav">
      <div className="container nav__inner">
        <Link href="/" className="brand" aria-label="TalNex home">
          <span className="brand__mark" aria-hidden="true">
            T
          </span>
          TalNex
        </Link>
        <nav className="nav__links" aria-label="Main">
          {signedIn ? (
            <form action={leave}>
              <button type="submit" className="button button--ghost">
                Sign out
              </button>
            </form>
          ) : (
            <Link className="button button--primary" href="/login">
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
