"use client";

import { useEffect, useRef } from "react";

// How far the button follows the pointer, as a share of the pointer's distance from its centre.
const PULL = 0.3;

/**
 * Pulls its child gently toward the pointer while the pointer is over it, and springs back when it leaves.
 * Only on devices with a precise pointer, and never for people who asked for reduced motion.
 * The offset goes into two CSS variables; the stylesheet does the moving.
 */
export function Magnetic({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!matchMedia("(pointer: fine)").matches || matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const move = (e: PointerEvent) => {
      const box = el.getBoundingClientRect();
      el.style.setProperty("--magnet-x", `${(e.clientX - (box.left + box.width / 2)) * PULL}px`);
      el.style.setProperty("--magnet-y", `${(e.clientY - (box.top + box.height / 2)) * PULL}px`);
      el.classList.add("magnet--active");
    };
    const leave = () => {
      el.style.removeProperty("--magnet-x");
      el.style.removeProperty("--magnet-y");
      el.classList.remove("magnet--active");
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
    };
  }, []);

  return (
    <span ref={ref} className="magnet">
      {children}
    </span>
  );
}
