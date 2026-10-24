import { Logo } from "@/components/ui/Logo";

/** The footer on public pages. */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap site-footer__inner">
        <span className="site-footer__line">
          <Logo href={null} small />
          Proof on every number. Humans decide, TalNex shows the evidence.
        </span>
        <span className="site-footer__copy">© {new Date().getFullYear()} TalNex</span>
      </div>
    </footer>
  );
}
