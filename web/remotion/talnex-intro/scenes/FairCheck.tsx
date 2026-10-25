import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Cross, Underline } from "../components/Marker";
import { FilmBase, FilmFrame, MiniScreen, STEPS } from "../components/Film";
import { Glyph, Verdict } from "../components/Verdict";
import { C, SAFE, display, lerp, mono, text, tw } from "../theme";

export const FAIR_DURATION = 200;

const Try: React.FC<{ n: number; at: number; time: string }> = ({ n, at, time }) => {
  const frame = useCurrentFrame();
  const t = tw(frame, at, 10);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 22,
        padding: "20px 0",
        borderBottom: `2px solid ${C.line}`,
        opacity: frame >= at ? 1 : 0,
        translate: `${lerp(24, 0, t)}px 0`,
      }}
    >
      <span style={{ ...text, fontWeight: 600, fontSize: 44, color: C.ink, width: 140 }}>Try {n}</span>
      <Glyph kind="broken" size={40} />
      <span style={{ ...text, fontSize: 40, color: C.broken, flex: 1 }}>Server error</span>
      <span style={{ ...mono, fontSize: 32, color: C.faint }}>{time}</span>
    </div>
  );
};

export const FairCheck: React.FC = () => {
  const frame = useCurrentFrame();
  const fw = 620;
  const k = fw / 560;
  const second = tw(frame, 84, 12);
  const write = tw(frame, 124, 34, (v) => v);
  const under = tw(frame, 160, 16);
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      {/* Frame 05, up close, already crossed out */}
      <div style={{ position: "absolute", left: SAFE.x, top: 120, translate: `${lerp(-60, 0, tw(frame, 0, 14))}px 0` }}>
        <FilmBase width={fw + 80 * k} k={k}>
          <div style={{ paddingLeft: 40 * k }}>
            <FilmFrame
              index={4}
              caption={STEPS[4].caption}
              width={fw}
              k={k}
              overlay={<Cross progress={1} w={160} h={160} style={{ right: -40, bottom: -44 }} />}
            >
              <MiniScreen screen="error" k={k} />
            </FilmFrame>
          </div>
        </FilmBase>
      </div>

      {/* The tries, then the second check */}
      <div style={{ position: "absolute", left: 1000, right: SAFE.x, top: 120 }}>
        <div style={{ ...display, fontSize: 84, color: C.ink, lineHeight: 1.02, opacity: tw(frame, 2, 10) }}>
          Never called broken
          <br />
          on one bad try.
        </div>
        <div style={{ marginTop: 34 }}>
          <Try n={1} at={20} time="00:41" />
          <Try n={2} at={38} time="00:52" />
          <Try n={3} at={56} time="01:04" />
        </div>
        <div
          style={{
            marginTop: 34,
            opacity: second,
            translate: `0 ${lerp(16, 0, second)}px`,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <span style={{ ...text, fontSize: 36, color: C.muted }}>Second check, screenshots only:</span>
          <span>
            <Verdict kind="broken" size={36} label="Agrees: broken" />
          </span>
        </div>
      </div>

      {/* The verdict, written in the margin with the marker */}
      <div
        style={{
          position: "absolute",
          left: SAFE.x + 10,
          top: 850,
          rotate: "-1.5deg",
          transformOrigin: "0 50%",
        }}
      >
        <div
          style={{
            ...display,
            fontSize: 92,
            color: C.marker,
            whiteSpace: "nowrap",
            clipPath: `inset(-20px ${100 - 100 * write}% -20px -20px)`,
          }}
        >
          Partly works. Search fails, every time.
        </div>
        <div style={{ position: "relative", height: 26, marginTop: 6 }}>
          <Underline progress={under} w={1270} h={22} style={{ left: 0, top: 0 }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
