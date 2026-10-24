"use client";

import { usePathname } from "next/navigation";

/** Pages that use the whole width: no sidebar, only the top bar, so a chat and a live site can sit side by side. */
export function isFocusPage(pathname: string): boolean {
  return pathname === "/walkthrough" || pathname.endsWith("/walkthrough");
}

/** The outer frame of the signed-in pages. It only decides whether the sidebar shows; everything inside is unchanged. */
export function ShellFrame({ children }: { children: React.ReactNode }) {
  const focus = isFocusPage(usePathname());
  return <div className={focus ? "shell shell--focus" : "shell"}>{children}</div>;
}
