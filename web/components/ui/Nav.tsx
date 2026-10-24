import Link from "next/link";

/** The top bar on public pages. The signed-in frame has its own navigation. */
export function Nav() {
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
          <Link className="button button--primary" href="/login">
            Sign in
          </Link>
        </nav>
      </div>
    </header>
  );
}
