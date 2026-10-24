import Link from "next/link";

import { ButtonLink } from "@/components/ui/Button";

const LINKS = [
  { href: "/#how", label: "How a check runs" },
  { href: "/#proof", label: "Sample result" },
  { href: "/about", label: "About" },
  { href: "/docs", label: "Docs" },
  { href: "/contact", label: "Contact" },
  { href: "/terms", label: "Terms" },
  { href: "/privacy", label: "Privacy" },
];

/**
 * The footer on public pages: the main button, the links in a row, and the name printed huge across the bottom,
 * wider than the screen and fading out.
 */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap site-footer__top">
        <ButtonLink href="/login" variant="primary" size="lg" magnetic>
          Check a project
        </ButtonLink>
        <nav className="site-footer__links" aria-label="Footer">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="site-footer__link">
              {link.label}
            </Link>
          ))}
        </nav>
        <p className="site-footer__copy">© {new Date().getFullYear()} TalNex. Proof on every number.</p>
      </div>

      <p className="site-footer__word" aria-hidden="true">
        TalNex
      </p>
    </footer>
  );
}
