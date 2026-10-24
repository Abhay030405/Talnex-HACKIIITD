import Link from "next/link";

import { auth, signOut } from "@/auth";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";

/** The top bar on public pages. The signed-in workspace has its own navigation. */
export async function Nav() {
  const signedIn = Boolean((await auth())?.user);

  async function leave() {
    "use server";
    await signOut({ redirectTo: "/" });
  }

  return (
    <header className="site-nav">
      <div className="wrap site-nav__inner">
        <Logo />
        <nav className="site-nav__links" aria-label="Main">
          <a className="site-nav__link" href="/#how">
            How it works
          </a>
          <Link className="site-nav__link" href="/about">
            About
          </Link>
          <Link className="site-nav__link" href="/docs">
            Docs
          </Link>
          {signedIn ? (
            <form action={leave}>
              <Button variant="ghost">Sign out</Button>
            </form>
          ) : (
            <ButtonLink href="/login" variant="primary">
              Sign in
            </ButtonLink>
          )}
        </nav>
      </div>
    </header>
  );
}
