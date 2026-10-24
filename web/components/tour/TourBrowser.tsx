"use client";

import { useState } from "react";

import type { TourShot } from "@/lib/tour";

/**
 * The right side of the walk-through: the live site as the guide's browser sees it, one picture after every action,
 * with a box on what was touched. The box is drawn in the picture's own coordinates, so it fits at any size.
 */
export function TourBrowser({
  shot,
  siteUrl,
  working,
  hasLive,
}: {
  shot: TourShot | null;
  siteUrl: string | null;
  working: boolean;
  hasLive: boolean;
}) {
  const [size, setSize] = useState<{ url: string; w: number; h: number } | null>(null);
  const known = shot && size && size.url === shot.url ? size : null;

  return (
    <section className="tour-browser" aria-label="The live site">
      <div className="tour-browser__bar">
        <span className="tour-browser__dots" aria-hidden="true" />
        <span className="tour-browser__address">{shot?.page || siteUrl || "no live link"}</span>
        {working && <span className="tour-browser__busy">working…</span>}
      </div>
      <div className="tour-browser__screen">
        {shot?.url ? (
          <div className="tour-shot">
            <img
              className="tour-shot__img"
              src={shot.url}
              alt={shot.label || "The live site"}
              onLoad={(e) => setSize({ url: shot.url!, w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            />
            {shot.box && known && (
              <svg className="tour-shot__overlay" viewBox={`0 0 ${known.w} ${known.h}`} preserveAspectRatio="none" aria-hidden="true">
                <rect
                  className="tour-shot__box"
                  x={shot.box.x}
                  y={shot.box.y}
                  width={shot.box.w}
                  height={shot.box.h}
                />
              </svg>
            )}
          </div>
        ) : (
          <p className="tour-browser__empty">
            {hasLive
              ? "The live site will appear here when the guide shows a step on it."
              : "This project has no live link, so there is no site to show. The tour is from the code."}
          </p>
        )}
      </div>
      {shot?.label && <p className="tour-browser__caption">{shot.label}</p>}
    </section>
  );
}
