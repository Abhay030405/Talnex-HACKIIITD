import type { Metadata } from "next";

import { Nav } from "@/components/ui/Nav";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "TalNex: proof of what actually works", template: "%s · TalNex" },
  description:
    "TalNex opens a project like a real person would and shows what actually works, so organizers and recruiters do not have to check by hand.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <Nav />
        <main id="main">{children}</main>
        <footer className="footer">
          <div className="container row row--between">
            <span>© TalNex. Proof on every number.</span>
            <span>Humans decide. TalNex shows the evidence.</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
