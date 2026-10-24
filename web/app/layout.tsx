import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";
import { Archivo } from "next/font/google";

import { auth } from "@/auth";
import { Nav } from "@/components/ui/Nav";
import { Shell } from "@/components/ui/Shell";
import { SiteFooter } from "@/components/ui/SiteFooter";
import { SmoothScroll } from "@/components/ui/SmoothScroll";

import "./globals.css";

// Condensed Archivo for display type: the stylesheet narrows it with font-stretch, so the width axis is loaded too.
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });

export const metadata: Metadata = {
  title: {
    default: "TalNex: proof of what actually works",
    template: "%s · TalNex",
  },
  description:
    "TalNex opens a project like a real person would and shows what actually works, so organizers and recruiters do not have to check by hand.",
};

/** Signed-in people with a role get their workspace frame; everyone else gets the public pages. */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = (await auth())?.user;

  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} ${archivo.variable}`}>
      <body>
        {user?.role ? (
          <Shell role={user.role} name={user.name || user.email || "You"}>
            {children}
          </Shell>
        ) : (
          <SmoothScroll>
            <a className="skip-link" href="#main">
              Skip to content
            </a>
            <Nav />
            <main id="main">{children}</main>
            <SiteFooter />
          </SmoothScroll>
        )}
      </body>
    </html>
  );
}
