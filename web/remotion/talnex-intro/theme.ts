// One place for every colour, font and easing in the film. Matches the TalNex site tokens (web/app/globals.css).
// This is a copy of the video project (C:/hackathon/talnex-intro/src) made to play live in the website through
// @remotion/player. The only changes: fonts come from the site's own self-hosted fonts (app/layout.tsx), and images
// come from public/intro/film/.
import { CSSProperties } from "react";
import { Easing, interpolate } from "remotion";

export const C = {
  paper: "#EDEFEC",
  surface: "#F6F7F5",
  raised: "#FFFFFF",
  ink: "#15181A",
  muted: "#454D4A",
  faint: "#646C69",
  line: "rgba(21,24,26,0.14)",
  lineSoft: "rgba(21,24,26,0.08)",
  lineStrong: "rgba(21,24,26,0.32)",

  film: "#1A1815",
  filmFrame: "#2A2722",
  filmEdge: "#E5A23A",
  filmHole: "#EDEFEC",

  marker: "#D7261E",

  works: "#16773A",
  worksSoft: "rgba(22,119,58,0.08)",
  worksLine: "rgba(22,119,58,0.35)",
  partly: "#8F5F00",
  partlySoft: "rgba(176,120,0,0.10)",
  partlyLine: "rgba(143,95,0,0.38)",
  broken: "#B42318",
  brokenSoft: "rgba(180,35,24,0.07)",
  brokenLine: "rgba(180,35,24,0.35)",
  untested: "#5B6360",
  testing: "#1D5FD1",
  testingSoft: "rgba(29,95,209,0.10)",

  mockBg: "#F4F5F2",
  mockSurface: "#FFFFFF",
  mockLine: "#A9AFAB",
  mockLineSoft: "#E1E4E0",
} as const;

export const FONT = {
  display: "var(--font-archivo), Archivo, sans-serif",
  text: "var(--font-geist-sans), Geist, sans-serif",
  mono: "var(--font-geist-mono), 'Geist Mono', monospace",
};

/** Archivo, condensed and bold: the headline voice. */
export const display: CSSProperties = {
  fontFamily: FONT.display,
  fontWeight: 700,
  fontStretch: "75%",
  fontVariationSettings: "'wdth' 75",
  letterSpacing: "-0.01em",
  lineHeight: 1,
};

export const text: CSSProperties = {
  fontFamily: FONT.text,
  fontWeight: 400,
};

export const mono: CSSProperties = {
  fontFamily: FONT.mono,
  fontWeight: 500,
  fontVariantNumeric: "tabular-nums",
};

export const MARKER_WIDTH = 7;

/** The house easing, cubic-bezier(.2,0,0,1). */
export const EASE = Easing.bezier(0.2, 0, 0, 1);

/** 0..1 progress of a move that starts at `start` and lasts `dur` frames. */
export const tw = (frame: number, start: number, dur: number, easing = EASE) =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Title-safe margins for 1920x1080. */
export const SAFE = { x: 140, y: 100 };
