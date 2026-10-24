"use client";

import { Player, type PlayerRef } from "@remotion/player";
import { useEffect, useRef } from "react";

import { TOTAL_DURATION, TalnexIntro } from "@/remotion/talnex-intro/TalnexIntro";

// The Remotion player for the hero (components/landing/HeroFilm.tsx). It lives here, with the film's own code, because
// Remotion sizes its player through an inline style; the website's components never use inline styles.
const FILL = { width: "100%" } as const;

/** The Remotion player itself, kept in its own file so it can load after the page. Silent, looping, 1920x1080. */
export function FilmPlayer({ onReady, controls }: { onReady: (ref: PlayerRef) => void; controls: boolean }) {
  const ref = useRef<PlayerRef>(null);

  useEffect(() => {
    if (ref.current) onReady(ref.current);
    // Only once, when the player first appears.
  }, []);

  return (
    <Player
      ref={ref}
      className="hero-film__player"
      style={FILL}
      component={TalnexIntro}
      durationInFrames={TOTAL_DURATION}
      fps={30}
      compositionWidth={1920}
      compositionHeight={1080}
      loop
      controls={controls}
      clickToPlay={controls}
      doubleClickToFullscreen={false}
      spaceKeyToPlayOrPause={false}
      initiallyMuted
    />
  );
}
