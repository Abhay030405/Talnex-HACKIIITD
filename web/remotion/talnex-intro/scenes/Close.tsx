import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Logo } from "../components/Logo";
import { Underline } from "../components/Marker";
import { C, SAFE, display, lerp, text, tw } from "../theme";

export const CLOSE_DURATION = 180;
const CUT = 76;

export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < CUT) {
    return (
      <AbsoluteFill style={{ background: C.paper }}>
        <div style={{ position: "absolute", left: SAFE.x + 20, top: 400, ...display, fontSize: 104, lineHeight: 1.12 }}>
          <div style={{ color: C.muted, opacity: frame >= 2 ? 1 : 0, translate: `0 ${lerp(18, 0, tw(frame, 2, 9))}px` }}>
            For hackathon organizers and recruiters.
          </div>
          <div style={{ color: C.ink, opacity: frame >= 26 ? 1 : 0, translate: `0 ${lerp(18, 0, tw(frame, 26, 9))}px` }}>
            Proof on every number. Humans decide.
          </div>
        </div>
      </AbsoluteFill>
    );
  }
  const f = frame - CUT;
  return (
    <AbsoluteFill style={{ background: C.paper, alignItems: "center", justifyContent: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", scale: String(lerp(1.04, 1, tw(f, 0, 30))) }}>
        <Logo size={170} />
        <div style={{ position: "relative", marginTop: 56 }}>
          <div style={{ ...text, fontSize: 46, color: C.muted, opacity: tw(f, 10, 14) }}>
            Proof of what actually works.
          </div>
          <Underline progress={tw(f, 26, 16)} w={640} h={22} style={{ left: -10, bottom: -30 }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
