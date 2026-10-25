import { AbsoluteFill, useCurrentFrame } from "remotion";
import { AnimatedMark, wordmark } from "../components/Logo";
import { C, display, lerp, text, tw } from "../theme";

// The logo assembles part by part (as in LogoIntro), the name follows, then the lockup lifts to make room for the line.
export const Enter: React.FC = () => {
  const frame = useCurrentFrame();
  const lift = tw(frame, 46, 20);
  const size = 162;
  return (
    <AbsoluteFill style={{ background: C.paper, alignItems: "center", justifyContent: "center" }}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          translate: `0 ${lerp(150, 0, lift)}px`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: size * 0.3 }}>
          <AnimatedMark height={size * 1.3} frame={(frame - 2) * 1.15} />
          <div style={{ overflow: "hidden", paddingBottom: 8 }}>
            <div
              style={{
                ...wordmark(size),
                translate: `${lerp(-40, 0, tw(frame, 24, 16))}px 0`,
                clipPath: `inset(0 ${100 - 100 * tw(frame, 24, 16)}% 0 0)`,
              }}
            >
              TalNex
            </div>
          </div>
        </div>

        <div
          style={{
            marginTop: 80,
            ...display,
            fontSize: 112,
            color: C.ink,
            opacity: frame >= 58 ? 1 : 0,
            translate: `0 ${lerp(20, 0, tw(frame, 58, 10))}px`,
          }}
        >
          TalNex checks it, frame by frame.
        </div>
        <div
          style={{
            marginTop: 34,
            maxWidth: 1240,
            textAlign: "center",
            ...text,
            fontSize: 42,
            lineHeight: 1.35,
            color: C.muted,
            opacity: tw(frame, 76, 14),
          }}
        >
          An AI agent opens the live link, uses it like a real person, and saves a screenshot at every step.
        </div>
      </div>
    </AbsoluteFill>
  );
};
