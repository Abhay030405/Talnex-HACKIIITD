"use client";

import { Pause, Play } from "lucide-react";
import dynamic from "next/dynamic";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import type { PlayerRef } from "@remotion/player";

// The Remotion film, played live in the page rather than as a video file. The player and the film's code load after
// the page itself, so the hero appears at once; until then the still below holds its place.
const FilmPlayer = dynamic(() => import("@/remotion/FilmPlayer").then((m) => m.FilmPlayer), {
  ssr: false,
  loading: () => <Still />,
});

function Still() {
  return (
    <Image
      className="hero-film__still"
      src="/intro/talnex-intro-poster.jpg"
      alt=""
      width={1920}
      height={1080}
      priority
    />
  );
}

/** The hero's film: plays while it is on screen, pauses when it is not, and can always be paused by hand. */
export function HeroFilm() {
  const frame = useRef<HTMLDivElement>(null);
  const player = useRef<PlayerRef>(null);
  const [reduced, setReduced] = useState(false);
  const [paused, setPaused] = useState(true);
  const userPaused = useRef(false);
  const visible = useRef(false);

  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setReduced(true);
      return;
    }
    const el = frame.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible.current = entry.isIntersecting;
        if (entry.isIntersecting && !userPaused.current) player.current?.play();
        else player.current?.pause();
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  function onReady(ref: PlayerRef) {
    player.current = ref;
    ref.addEventListener("play", () => setPaused(false));
    ref.addEventListener("pause", () => setPaused(true));
    if (visible.current && !reduced && !userPaused.current) ref.play();
  }

  function toggle() {
    const ref = player.current;
    if (!ref) return;
    userPaused.current = ref.isPlaying();
    ref.toggle();
  }

  return (
    <div className="hero-film" ref={frame}>
      <FilmPlayer onReady={onReady} controls={reduced} />
      {!reduced && (
        <button
          type="button"
          className="film-toggle"
          onClick={toggle}
          aria-label={paused ? "Play the film" : "Pause the film"}
        >
          {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
        </button>
      )}
    </div>
  );
}
