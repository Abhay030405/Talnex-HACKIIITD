// LogoIntro: a short reveal of the TalNex mark, played full-screen before the website appears.
// Each part of the logo is its own transparent layer cut from the original PNG (see public/logo-*.png),
// so the final frame is pixel-for-pixel the brand mark on the paper colour.
import { CSSProperties } from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, display, EASE, lerp, tw } from "./theme";

export const LOGO_INTRO_DURATION = 78; // 2.6 s at 30 fps

// Layers are 715x645 crops of the 1254x1254 source (offset 270,330). The visible mark spans 605 px tall.
const LAYER_W = 715;
const LAYER_H = 645;
const LOGO_PX = 410; // on-screen height of the mark
const SCALE = LOGO_PX / 605;

// Timings (frames).
export const T = {
  bar: { start: 0, dur: 15 },
  dots: [8, 10, 12],
  stem: { start: 10, dur: 17 },
  check: { start: 24, dur: 18 },
  sparkle: { start: 40, dur: 11 },
  word: { start: 45, dur: 16 },
} as const;

// Dot centres in layer space.
export const DOTS = [
  [145, 72.4],
  [191.5, 72.4],
  [238.2, 72.4],
] as const;

const layer: CSSProperties = {
  position: "absolute",
  left: 0,
  top: 0,
  width: LAYER_W,
  height: LAYER_H,
};

const Part: React.FC<{ name: string; style?: CSSProperties }> = ({ name, style }) => (
  <Img src={staticFile(`intro/film/logo-${name}.png`)} style={{ ...layer, ...style }} />
);

/** Half-plane clip: shows everything whose projection on `d` is <= `t` (layer px). */
export const wipe = (t: number, dx: number, dy: number) => {
  const len = Math.hypot(dx, dy);
  const ux = dx / len;
  const uy = dy / len;
  const nx = -uy;
  const ny = ux;
  const big = 2000;
  const px = ux * t;
  const py = uy * t;
  const pts = [
    [px + nx * big, py + ny * big],
    [px - nx * big, py - ny * big],
    [px - nx * big - ux * big, py - ny * big - uy * big],
    [px + nx * big - ux * big, py + ny * big - uy * big],
  ];
  return `polygon(${pts.map(([x, y]) => `${x.toFixed(2)}px ${y.toFixed(2)}px`).join(", ")})`;
};

export const LogoIntro: React.FC<{ wordmark?: boolean }> = ({ wordmark = true }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 1. Browser bar: slides in from the left with a skew that settles, revealed left to right.
  const pBar = tw(frame, T.bar.start, T.bar.dur);
  const barX = lerp(-110, 0, pBar);
  const barSkew = lerp(-14, 0, pBar);
  const barReveal = lerp(0, LAYER_W, pBar);
  const barOpacity = interpolate(frame, [0, 5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // 2. T stem: drops in from above, revealed top to bottom, tucked behind the bar.
  const pStem = tw(frame, T.stem.start, T.stem.dur);
  const stemY = lerp(-40, 0, pStem);
  const stemBottom = lerp(149, 627, pStem);
  const stemOpacity = interpolate(frame, [T.stem.start, T.stem.start + 5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 3. Check ribbon: drawn from its lower-left to its upper-right.
  const pCheck = tw(frame, T.check.start, T.check.dur);
  const checkT = lerp(-24, 284, pCheck);

  // 4. Sparkle: quick scale + rotate twinkle, then a faint echo as the glint.
  const sp = spring({ frame: frame - T.sparkle.start, fps, config: { damping: 15, stiffness: 220, mass: 0.6 } });
  const sparkleRot = lerp(-75, 0, sp);
  const glintP = interpolate(frame, [T.sparkle.start + 5, T.sparkle.start + 17], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE,
  });

  // 5. Whole-mark settle: a 1.5% scale that comes to rest by ~1.9 s, then holds still.
  const settle = lerp(0.985, 1, tw(frame, 0, 57));

  // Optional wordmark.
  const pWord = tw(frame, T.word.start, T.word.dur);
  const wordSize = 96;
  const gap = 46;
  const groupShift = wordmark ? -(wordSize * 0.78 + gap) / 2 : 0;

  const SPARK_ORIGIN = "639px 180px";

  return (
    <AbsoluteFill style={{ backgroundColor: C.paper }}>
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: LAYER_W,
          height: LAYER_H,
          transform: `translate(-50%, -50%) translateY(${groupShift}px) scale(${SCALE * settle})`,
        }}
      >
        {/* Stem first so it sits behind the bar while dropping. */}
        <Part
          name="stem"
          style={{
            transform: `translateY(${stemY}px)`,
            clipPath: `inset(0px 0px ${(LAYER_H - stemBottom).toFixed(2)}px 0px)`,
            opacity: stemOpacity,
          }}
        />

        <Part name="check" style={{ clipPath: wipe(checkT, 1, -1) }} />

        <div
          style={{
            ...layer,
            opacity: barOpacity,
            transformOrigin: "19px 285px",
            transform: `translateX(${barX}px) skewX(${barSkew}deg)`,
          }}
        >
          <Part name="bar" style={{ clipPath: `inset(0px ${(LAYER_W - barReveal).toFixed(2)}px 0px 0px)` }} />
          {DOTS.map(([cx, cy], i) => {
            const s = spring({
              frame: frame - T.dots[i],
              fps,
              config: { damping: 14, stiffness: 260, mass: 0.5 },
            });
            return (
              <Part
                key={i}
                name={`dot${i + 1}`}
                style={{ transformOrigin: `${cx}px ${cy}px`, transform: `scale(${s})` }}
              />
            );
          })}
        </div>

        {/* Glint: a faint echo of the sparkle that grows and fades. */}
        <Part
          name="sparkle"
          style={{
            transformOrigin: SPARK_ORIGIN,
            transform: `scale(${lerp(1, 1.9, glintP)}) rotate(${lerp(0, 45, glintP)}deg)`,
            opacity: glintP > 0 ? 0.22 * (1 - glintP) : 0,
          }}
        />
        <Part
          name="sparkle"
          style={{
            transformOrigin: SPARK_ORIGIN,
            transform: `scale(${sp}) rotate(${sparkleRot}deg)`,
          }}
        />
      </div>

      {wordmark ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "50%",
            textAlign: "center",
            transform: `translateY(${LOGO_PX / 2 + groupShift + gap + lerp(14, 0, pWord)}px)`,
            opacity: pWord,
            ...display,
            color: C.ink,
            fontSize: wordSize,
            letterSpacing: "-0.005em",
          }}
        >
          TalNex
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
