"use client";

import { useEffect, useState } from "react";

import { proofClip } from "@/lib/report-format";
import type { ProofStep, Verdict } from "@/lib/types";

const FRAME_MS = 1500;

/**
 * The claim's test played back as a clip: each screenshot with what the agent did, ending on the verdict stamp.
 * Nothing plays until the viewer presses play. Links are short-lived, so a page left open may need a refresh.
 */
export function ProofClip({ steps, verdict }: { steps: ProofStep[]; verdict: Verdict | null }) {
  const clip = proofClip(steps, verdict);
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(false);
  const last = clip ? clip.frames.length - 1 : 0;

  useEffect(() => {
    if (!playing) return;
    if (at >= last) {
      setPlaying(false);
      return;
    }
    const timer = setTimeout(() => setAt(at + 1), FRAME_MS);
    return () => clearTimeout(timer);
  }, [playing, at, last]);

  if (!clip) return null;
  const frame = clip.frames[at];
  const play = () => {
    if (at >= last) setAt(0);
    setPlaying(!playing);
  };

  return (
    <figure className="proof-clip">
      <div className="proof-clip__screen">
        {/* A short-lived storage link: Next's image optimiser would cache it past its life. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="proof-clip__img" src={frame.url} alt={frame.caption} />
        {at === last && (
          <span className={`proof-clip__stamp proof-clip__stamp--${clip.stamp.tone}`}>{clip.stamp.text}</span>
        )}
      </div>
      <figcaption className="proof-clip__caption" aria-live="polite">
        <span className="proof-step__action">{frame.caption}</span>
        {frame.seen && <span className="proof-step__observed">Seen: {frame.seen}</span>}
      </figcaption>
      <div className="proof-clip__controls">
        <button type="button" className="button button--ghost" onClick={() => setAt(Math.max(0, at - 1))} disabled={at === 0}>
          Back
        </button>
        <button type="button" className="button button--ghost" onClick={play}>
          {playing ? "Pause" : at >= last ? "Play again" : "Play"}
        </button>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => setAt(Math.min(last, at + 1))}
          disabled={at === last}
        >
          Next
        </button>
        <span className="meta">
          {at + 1} / {clip.frames.length}
        </span>
      </div>
    </figure>
  );
}
