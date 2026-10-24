import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C, SAFE, display, lerp, tw } from "../theme";

// Words slam in one at a time: a short, hard scale-down from 106% with no fade tail.
const Slam: React.FC<{ at: number; children: React.ReactNode; color?: string }> = ({ at, children, color = C.ink }) => {
  const frame = useCurrentFrame();
  const t = tw(frame, at, 7);
  return (
    <span
      style={{
        display: "inline-block",
        color,
        opacity: frame >= at ? 1 : 0,
        scale: String(lerp(1.08, 1, t)),
        transformOrigin: "50% 80%",
        marginRight: "0.22em",
      }}
    >
      {children}
    </span>
  );
};

export const ColdOpen: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <div
        style={{
          position: "absolute",
          left: SAFE.x + 20,
          top: 300,
          ...display,
          fontSize: 230,
          lineHeight: 0.98,
          scale: String(lerp(1, 1.025, tw(frame, 0, 80, (x) => x))),
          transformOrigin: "0 50%",
        }}
      >
        <div>
          <Slam at={4}>{"“It works,”"}</Slam>
        </div>
        <div>
          <Slam at={24} color={C.muted}>
            says
          </Slam>
          <Slam at={29} color={C.muted}>
            the
          </Slam>
          <Slam at={34}>README.</Slam>
        </div>
      </div>
    </AbsoluteFill>
  );
};
