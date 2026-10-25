"use client";

import { useEffect, useRef, useState } from "react";

const SEEN_KEY = "tn-intro-seen";
// If the clip cannot play (blocked autoplay, missing file), the page is never held back longer than this.
const GIVE_UP_MS = 4000;
const FADE_MS = 600;

/**
 * Runs before the page paints: a visitor who has already seen the intro this session, or who asked for reduced motion,
 * never sees it, not even for a frame. The stylesheet hides the splash when <html data-intro="skip"> is set.
 */
export const INTRO_GATE = `try{if(sessionStorage.getItem("${SEEN_KEY}")||matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.dataset.intro="skip"}catch(e){}`;

/** The animated logo, played once per visit on top of the page, then faded away. Click or any key skips it. */
export function IntroSplash() {
  const [state, setState] = useState<"playing" | "leaving" | "gone">("playing");
  const video = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (document.documentElement.dataset.intro === "skip") {
      setState("gone");
      return;
    }
    const leave = () => setState((s) => (s === "playing" ? "leaving" : s));
    // Counted from the page starting to load, not from this code running, so a slow start never adds to the wait.
    const timer = setTimeout(leave, Math.max(0, GIVE_UP_MS - performance.now()));
    window.addEventListener("keydown", leave, { once: true });
    video.current?.play().catch(leave);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", leave);
    };
  }, []);

  useEffect(() => {
    if (state !== "leaving") return;
    try {
      sessionStorage.setItem(SEEN_KEY, "1");
    } catch {
      // Private windows may refuse storage; the intro then simply plays again next time.
    }
    const timer = setTimeout(() => setState("gone"), FADE_MS);
    return () => clearTimeout(timer);
  }, [state]);

  if (state === "gone") return null;

  return (
    <div
      className={state === "leaving" ? "intro intro--leaving" : "intro"}
      aria-hidden="true"
      onClick={() => setState("leaving")}
    >
      <video
        ref={video}
        className="intro__video"
        autoPlay
        muted
        playsInline
        preload="auto"
        poster="/intro/logo-intro-poster.png"
        src="/intro/logo-intro.mp4"
        onEnded={() => setState("leaving")}
        onError={() => setState("leaving")}
      />
    </div>
  );
}
