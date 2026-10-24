import { CSSProperties, ReactNode } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Question } from "../components/Marker";
import { C, SAFE, display, lerp, mono, text, tw } from "../theme";

// A clipping cuts in fast, then a red question mark is scrawled beside it.
const Clip: React.FC<{ at: number; left: number; top: number; rotate: number; children: ReactNode }> = ({
  at,
  left,
  top,
  rotate,
  children,
}) => {
  const frame = useCurrentFrame();
  const t = tw(frame, at, 8);
  return (
    <div
      style={{
        position: "absolute",
        left,
        top,
        opacity: frame >= at ? 1 : 0,
        translate: `0 ${lerp(26, 0, t)}px`,
        rotate: `${rotate}deg`,
      }}
    >
      {children}
      <Question
        progress={tw(frame, at + 10, 14)}
        w={84} h={112} style={{ right: -96, top: -70 }}
      />
    </div>
  );
};

const slip: CSSProperties = {
  background: C.raised,
  border: `2px solid ${C.line}`,
  borderRadius: 14,
  boxSizing: "border-box",
};

export const NobodyChecks: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <div
        style={{
          position: "absolute",
          left: SAFE.x + 20,
          top: SAFE.y + 60,
          ...display,
          fontSize: 150,
          color: C.ink,
          opacity: frame >= 2 ? 1 : 0,
          translate: `0 ${lerp(18, 0, tw(frame, 2, 9))}px`,
        }}
      >
        Nobody has time to check.
      </div>

      {/* A project link */}
      <Clip at={14} left={SAFE.x + 20} top={560} rotate={-1.2}>
        <div style={{ ...slip, width: 470, padding: "26px 30px", ...text, fontSize: 34, color: C.ink }}>
          <span style={{ color: C.faint }}>https://</span>captionbuddy.app
        </div>
      </Clip>

      {/* A demo video thumbnail */}
      <Clip at={26} left={760} top={500} rotate={0.8}>
        <div style={{ width: 440, height: 248, borderRadius: 14, background: C.film, position: "relative" }}>
          <svg width="92" height="92" viewBox="0 0 24 24" style={{ position: "absolute", left: 174, top: 78 }}>
            <path d="M8 5v14l11-7z" fill={C.filmHole} />
          </svg>
          <span style={{ position: "absolute", right: 20, bottom: 16, ...mono, fontSize: 26, color: C.filmEdge }}>2:14</span>
          <span style={{ position: "absolute", left: 22, bottom: 16, ...text, fontSize: 26, color: C.filmHole, opacity: 0.8 }}>
            Demo
          </span>
        </div>
      </Clip>

      {/* A resume line */}
      <Clip at={38} left={1300} top={580} rotate={-0.6}>
        <div style={{ ...slip, width: 470, padding: "24px 30px", ...text, fontSize: 32, lineHeight: 1.3, color: C.ink }}>
          Built an AI caption app
          <br />
          <span style={{ color: C.muted }}>used by 2,000 people.</span>
        </div>
      </Clip>
    </AbsoluteFill>
  );
};
