"use client";

import { useState } from "react";

const LONG = 280;

/** Long text clamped to a few lines with a "Show more" toggle; short text shown as it is. */
export function ShowMore({ text, className }: { text: string; className: string }) {
  const [open, setOpen] = useState(false);
  if (text.length <= LONG) return <p className={className}>{text}</p>;
  return (
    <div className="show-more">
      <p className={open ? className : `${className} show-more__text--clamped`}>{text}</p>
      <button type="button" className="show-more__toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Show less" : "Show more"}
      </button>
    </div>
  );
}
