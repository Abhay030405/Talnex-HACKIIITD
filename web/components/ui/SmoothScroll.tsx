"use client";

import { ReactLenis } from "lenis/react";
import { useEffect, useState } from "react";

/**
 * Smooth, eased scrolling for the whole page (Lenis). It stays off for people who ask their system for less motion,
 * and anchor links like "How it works" glide to their section instead of jumping.
 */
export function SmoothScroll({ children }: { children: React.ReactNode }) {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setEnabled(!query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  if (!enabled) return <>{children}</>;
  return (
    <ReactLenis root options={{ lerp: 0.12, anchors: { offset: -80 }, autoRaf: true }}>
      {children}
    </ReactLenis>
  );
}
