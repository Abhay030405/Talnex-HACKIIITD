"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { CalendarIcon, DocsIcon, PlusIcon, UsersIcon } from "@/components/ui/Icons";

const ICONS = { users: UsersIcon, calendar: CalendarIcon, plus: PlusIcon, docs: DocsIcon };

export interface ShellNavItem {
  href: string;
  label: string;
  icon: keyof typeof ICONS;
  /** Pages under these paths also light this item up, like a candidate's page for "Candidates". */
  also?: string[];
}

/** Whether a link is the page the person is on. "/events" lights for "/events/1" but not for "/eventsx". */
export function isActive(pathname: string, item: ShellNavItem): boolean {
  const under = (base: string) => pathname === base || pathname.startsWith(`${base}/`);
  return under(item.href) || (item.also ?? []).some(under);
}

export function ShellNav({ items }: { items: ShellNavItem[] }) {
  const pathname = usePathname();
  return (
    <nav className="shell__nav" aria-label="Workspace">
      {items.map((item) => {
        const Icon = ICONS[item.icon];
        const active = isActive(pathname, item);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={active ? "shell__link shell__link--active" : "shell__link"}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={18} />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
