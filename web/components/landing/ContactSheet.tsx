"use client";

import { useEffect, useRef, useState } from "react";

// One made-up check of a todo app, frame by frame, the way TalNex keeps it: a screenshot at every step.
// Frame 5 fails on purpose, so the sheet ends the way most real projects do: partly works.
const FRAMES = [
  { screen: "load", caption: "Open the site", passed: true },
  { screen: "type", caption: "Type an item", passed: true },
  { screen: "click", caption: "Click Add", passed: true },
  { screen: "list", caption: "Item is in the list", passed: true },
  { screen: "error", caption: "Search “milk”", passed: false },
  { screen: "reload", caption: "Reload, still there", passed: true },
] as const;

type Screen = (typeof FRAMES)[number]["screen"];

const FRAME_MS = 1400;
const HOLD_MS = 4200;

/** A tiny screenshot of the todo app at one step. Drawn with plain blocks, so it reads at thumbnail size. */
function MiniScreen({ screen }: { screen: Screen }) {
  if (screen === "error") {
    return (
      <div className="mini mini--error">
        <span className="mini__code">500</span>
        <span className="mini__line">Internal server error</span>
      </div>
    );
  }
  const typed = screen !== "load";
  const added = screen === "list" || screen === "reload";
  return (
    <div className="mini">
      <span className="mini__title">Todos</span>
      <span className="mini__row">
        <span className={typed && !added ? "mini__input mini__input--typed" : "mini__input"}>
          {typed && !added ? "Milk" : ""}
        </span>
        <span className="mini__add">
          Add
          {screen === "click" && <span className="mini__tap" />}
        </span>
      </span>
      {added && <span className="mini__item mini__item--new">Milk</span>}
      <span className="mini__item">Bread</span>
      <span className="mini__item">Call the bank</span>
    </div>
  );
}

/** The china-marker marks an editor draws on a contact sheet. pathLength=1 lets the stylesheet draw them on. */
function Mark({ kind }: { kind: "circle" | "tick" | "cross" }) {
  if (kind === "circle") {
    return (
      <svg className="mark mark--circle" viewBox="0 0 220 160" preserveAspectRatio="none" aria-hidden="true">
        <path
          pathLength={1}
          d="M30 40 C 60 8, 180 4, 205 45 C 226 85, 200 148, 112 152 C 30 156, 4 116, 12 76 C 18 46, 52 24, 96 18"
        />
      </svg>
    );
  }
  if (kind === "tick") {
    return (
      <svg className="mark mark--tick" viewBox="0 0 60 50" aria-hidden="true">
        <path pathLength={1} d="M6 28 L 22 44 L 54 6" />
      </svg>
    );
  }
  return (
    <svg className="mark mark--cross" viewBox="0 0 60 60" aria-hidden="true">
      <path pathLength={1} d="M8 8 L 52 54" />
      <path pathLength={1} d="M52 6 L 10 52" />
    </svg>
  );
}

/**
 * The hero: a strip of film with the agent's screenshots, marked up as it goes. The current frame gets a circle,
 * passed frames a tick, the failed one a cross, and the sheet ends with the verdict written in the margin.
 * `still` shows the finished sheet with no movement (also what reduced motion gets).
 */
export function ContactSheet({ still = false, only }: { still?: boolean; only?: number[] }) {
  const frames = FRAMES.map((f, i) => ({ ...f, n: i })).filter((f) => !only || only.includes(f.n));
  const [step, setStep] = useState<number>(FRAMES.length);
  const strip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (still || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let current = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setStep(current);
      const el = strip.current?.querySelector<HTMLElement>(`[data-frame="${current}"]`);
      if (el && strip.current)
        strip.current.scrollTo({ left: el.offsetLeft - strip.current.clientWidth / 3, behavior: "smooth" });
      const wait = current === FRAMES.length ? HOLD_MS : FRAME_MS;
      current = current === FRAMES.length ? 0 : current + 1;
      timer = setTimeout(tick, wait);
    };
    tick();
    return () => clearTimeout(timer);
  }, [still]);

  const done = step >= FRAMES.length;

  return (
    <figure
      className={still ? "sheet sheet--still" : "sheet"}
      aria-label="Example: TalNex checking a todo app, one screenshot per step"
    >
      <div className="sheet__film">
        <span className="sheet__holes" aria-hidden="true" />
        <div className="sheet__strip" ref={strip}>
          {frames.map((f) => (
            <div key={f.n} className="frame" data-frame={f.n}>
              <div className="frame__screen">
                <MiniScreen screen={f.screen} />
                {f.n === step && <Mark kind="circle" />}
                {f.n < step && <Mark kind={f.passed ? "tick" : "cross"} />}
              </div>
              <span className="frame__edge">
                <span className="frame__num">{String(f.n + 1).padStart(2, "0")}</span>
                {f.caption}
              </span>
            </div>
          ))}
        </div>
        <span className="sheet__holes" aria-hidden="true" />
      </div>
      <figcaption className={done ? "sheet__verdict sheet__verdict--shown" : "sheet__verdict"}>
        <span className="sheet__scrawl">Partly works. Search fails, every time.</span>
        <svg className="sheet__underline" viewBox="0 0 300 12" preserveAspectRatio="none" aria-hidden="true">
          <path pathLength={1} d="M2 8 C 80 2, 200 12, 298 4" />
        </svg>
      </figcaption>
    </figure>
  );
}
