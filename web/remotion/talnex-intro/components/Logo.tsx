// The TalNex logo (the real mark from public/logo-*.png) and the name in condensed type.
import { CSSProperties } from "react";
import { Img, interpolate, spring, staticFile, useVideoConfig } from "remotion";
import { DOTS, T, wipe } from "../LogoIntro";
import { C, EASE, display, lerp, tw } from "../theme";

// The visible mark inside the 715x645 layer crops (and at 289,349 in the 1254x1254 logo-alpha.png).
const VIS = { x: 19, y: 19, w: 676, h: 608 };
const ALPHA = { size: 1254, x: 289, y: 349 };
const LAYER_W = 715;
const LAYER_H = 645;

export const markWidth = (height: number) => (height * VIS.w) / VIS.h;

/** The finished mark, cropped tight to its visible pixels. */
export const Mark: React.FC<{ height: number; style?: CSSProperties }> = ({ height, style }) => {
  const s = height / VIS.h;
  return (
    <div style={{ position: "relative", width: VIS.w * s, height, overflow: "hidden", flex: "none", ...style }}>
      <Img
        src={staticFile("intro/film/logo-alpha.png")}
        style={{
          position: "absolute",
          left: -ALPHA.x * s,
          top: -ALPHA.y * s,
          width: ALPHA.size * s,
          height: ALPHA.size * s,
          maxWidth: "none",
        }}
      />
    </div>
  );
};

const layer: CSSProperties = { position: "absolute", left: 0, top: 0, width: LAYER_W, height: LAYER_H };
const Part: React.FC<{ name: string; style?: CSSProperties }> = ({ name, style }) => (
  <Img src={staticFile(`intro/film/logo-${name}.png`)} style={{ ...layer, ...style }} />
);

/**
 * The mark assembling part by part, the same choreography as LogoIntro: bar slides in, dots pop,
 * stem drops, check wipes, sparkle twinkles. `frame` is the mark's own clock (0 = start).
 */
export const AnimatedMark: React.FC<{ height: number; frame: number }> = ({ height, frame }) => {
  const { fps } = useVideoConfig();
  const s = height / VIS.h;
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

  const pBar = tw(frame, T.bar.start, T.bar.dur);
  const pStem = tw(frame, T.stem.start, T.stem.dur);
  const stemBottom = lerp(149, 627, pStem);
  const checkT = lerp(-24, 284, tw(frame, T.check.start, T.check.dur));
  const sp = spring({ frame: frame - T.sparkle.start, fps, config: { damping: 15, stiffness: 220, mass: 0.6 } });
  const glintP = interpolate(frame, [T.sparkle.start + 5, T.sparkle.start + 17], [0, 1], { ...clamp, easing: EASE });
  const SPARK_ORIGIN = "639px 180px";

  return (
    <div style={{ position: "relative", width: VIS.w * s, height, flex: "none" }}>
      <div
        style={{
          ...layer,
          transformOrigin: "0 0",
          transform: `scale(${s}) translate(${-VIS.x}px, ${-VIS.y}px)`,
        }}
      >
        <Part
          name="stem"
          style={{
            transform: `translateY(${lerp(-40, 0, pStem)}px)`,
            clipPath: `inset(0px 0px ${(LAYER_H - stemBottom).toFixed(2)}px 0px)`,
            opacity: interpolate(frame, [T.stem.start, T.stem.start + 5], [0, 1], clamp),
          }}
        />
        <Part name="check" style={{ clipPath: wipe(checkT, 1, -1) }} />
        <div
          style={{
            ...layer,
            opacity: interpolate(frame, [0, 5], [0, 1], clamp),
            transformOrigin: "19px 285px",
            transform: `translateX(${lerp(-110, 0, pBar)}px) skewX(${lerp(-14, 0, pBar)}deg)`,
          }}
        >
          <Part name="bar" style={{ clipPath: `inset(0px ${(LAYER_W - lerp(0, LAYER_W, pBar)).toFixed(2)}px 0px 0px)` }} />
          {DOTS.map(([cx, cy], i) => (
            <Part
              key={i}
              name={`dot${i + 1}`}
              style={{
                transformOrigin: `${cx}px ${cy}px`,
                transform: `scale(${spring({ frame: frame - T.dots[i], fps, config: { damping: 14, stiffness: 260, mass: 0.5 } })})`,
              }}
            />
          ))}
        </div>
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
          style={{ transformOrigin: SPARK_ORIGIN, transform: `scale(${sp}) rotate(${lerp(-75, 0, sp)}deg)` }}
        />
      </div>
    </div>
  );
};

/** Wordmark style shared by every lockup. */
export const wordmark = (size: number): CSSProperties => ({
  ...display,
  color: C.ink,
  fontSize: size * 1.05,
  letterSpacing: "-0.005em",
});

/** Lockup: the mark beside the "TalNex" wordmark. `size` is the wordmark's cap scale (as before). */
export const Logo: React.FC<{ size: number; nameStyle?: CSSProperties }> = ({ size, nameStyle }) => (
  <div style={{ display: "flex", alignItems: "center", gap: size * 0.3 }}>
    <Mark height={size * 1.3} />
    <span style={{ ...wordmark(size), ...nameStyle }}>TalNex</span>
  </div>
);
