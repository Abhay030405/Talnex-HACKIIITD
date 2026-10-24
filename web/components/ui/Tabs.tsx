"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useRef, useState } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: React.ReactNode;
}

/**
 * Accessible tabs: role tablist/tab/tabpanel, arrow keys, Home and End. With `param`, the open tab is kept in the
 * address (?tab=projects) so a refresh or a shared link opens the same tab. Every panel is rendered; the others are
 * hidden, so nothing is fetched again when switching.
 */
export function Tabs({ tabs, initial, param, label }: { tabs: TabItem[]; initial?: string; param?: string; label: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const base = useId();
  const first = tabs.find((t) => t.id === initial)?.id ?? tabs[0]?.id;
  const [open, setOpen] = useState(first);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function choose(id: string, focus = false) {
    setOpen(id);
    if (focus) refs.current[tabs.findIndex((t) => t.id === id)]?.focus();
    if (param) {
      const next = new URLSearchParams(search.toString());
      next.set(param, id);
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    }
  }

  function onKey(e: React.KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const to = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: last }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    choose(tabs[(to + tabs.length) % tabs.length].id, true);
  }

  return (
    <div className="tabs">
      <div className="tabs__list" role="tablist" aria-label={label}>
        {tabs.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`${base}-${t.id}-tab`}
            aria-controls={`${base}-${t.id}-panel`}
            aria-selected={open === t.id}
            tabIndex={open === t.id ? 0 : -1}
            className="tabs__tab"
            onClick={() => choose(t.id)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`${base}-${t.id}-panel`}
          aria-labelledby={`${base}-${t.id}-tab`}
          hidden={open !== t.id}
          className="tabs__panel"
          tabIndex={0}
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}
