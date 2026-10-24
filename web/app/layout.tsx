import type { Metadata } from "next";

import { auth } from "@/auth";
import { Nav } from "@/components/ui/Nav";
import { Shell } from "@/components/ui/Shell";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "TalNex: proof of what actually works", template: "%s · TalNex" },
  description:
    "TalNex opens a project like a real person would and shows what actually works, so organizers and recruiters do not have to check by hand.",
};

/** Signed-in people with a role get their workspace frame; everyone else gets the public pages. */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = (await auth())?.user;

  return (
    <html lang="en">
      <body>
        {user?.role ? (
          <Shell role={user.role} name={user.name || user.email || "You"}>
            {children}
          </Shell>
        ) : (
          <>
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
          </>
        )}
      </body>
    </html>
  );
}
