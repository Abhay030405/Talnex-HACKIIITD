import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Circle, Cross, Tick } from "../components/Marker";
import { FilmBase, FilmFrame, MiniScreen, STEPS } from "../components/Film";
import { C, SAFE, display, lerp, mono, text, tw } from "../theme";

// Layout of the strip in world pixels (scale 1).
const W = 560;
const GAP = 64;
const PITCH = W + GAP;
const LEADER = 1000;
const SPAN = STEPS.length * PITCH - GAP;
const FILM_W = LEADER * 2 + SPAN;
const FILM_H = 16 * 2 + 16 * 2 + 22 * 2 + W * 0.75 + 16 + 34;
const TOP = 300;

// Timing (frames, local to this scene).
const ENTER = 24;
const FIRST = 30;
const STEP = 50;
export const stepStart = (i: number) => FIRST + i * STEP;
const PULL = stepStart(STEPS.length - 1) + STEP + 8;
export const STRIP_DURATION = PULL + 60;

const OVERVIEW_SCALE = 1600 / SPAN;

export const Strip: React.FC = () => {
  const frame = useCurrentFrame();

  // Camera: which frame we are looking at, eased between steps.
  let idx = 0;
  for (let i = 1; i < STEPS.length; i++) idx += tw(frame, stepStart(i) - 8, 20);
  const trackX = 960 - (LEADER + idx * PITCH + W / 2);
  const enterX = lerp(1920, 0, tw(frame, 0, ENTER));
  const pull = tw(frame, PULL, 34);
  const s = lerp(1, OVERVIEW_SCALE, pull);
  const overX = 960 - OVERVIEW_SCALE * (LEADER + SPAN / 2);
  const overY = 560 - (OVERVIEW_SCALE * FILM_H) / 2;
  const x = lerp(trackX + enterX, overX, pull);
  const y = lerp(TOP, overY, pull);

  const current = Math.min(STEPS.length - 1, Math.max(0, Math.floor((frame - FIRST) / STEP)));

  return (
    <AbsoluteFill style={{ background: C.paper, overflow: "hidden" }}>
      {/* What is being checked, and a running clock */}
      <div
        style={{
          position: "absolute",
          left: SAFE.x + 20,
          right: SAFE.x + 20,
          top: SAFE.y + 10,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          opacity: 1 - tw(frame, PULL, 8),
        }}
      >
        <div style={{ ...display, fontSize: 84, color: C.ink }}>
          Claim: <span style={{ color: C.muted }}>you can add an item and search for it.</span>
        </div>
        <div style={{ ...mono, fontSize: 36, color: C.muted }}>
          {String(Math.min(current + 1, 6)).padStart(2, "0")}/06
        </div>
      </div>

      {/* The world: the film strip, moved by the camera */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          transformOrigin: "0 0",
          translate: `${x}px ${y}px`,
          scale: String(s),
        }}
      >
        <FilmBase width={FILM_W}>
          <div style={{ display: "flex", gap: GAP, paddingLeft: LEADER }}>
            {STEPS.map((st, i) => {
              const s0 = stepStart(i);
              const exposed = tw(frame, s0 - 4, 6);
              const end = s0 + STEP - 6;
              const circleIn = tw(frame, s0 + 4, 14);
              const circleOut = interpolate(frame, [end, end + 6], [1, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              const mark = tw(frame, end + 2, 14);
              return (
                <FilmFrame
                  key={i}
                  index={i}
                  caption={st.caption}
                  width={W}
                  k={1}
                  overlay={
                    <>
                      <Circle
                        progress={circleIn}
                        w={W + 68} h={W * 0.75 + 68} style={{ left: -34, top: -34, opacity: circleOut }}
                      />
                      {st.passed ? (
                        <Tick progress={mark} w={120} h={100} style={{ right: -26, bottom: -30 }} />
                      ) : (
                        <Cross progress={mark} w={130} h={130} style={{ right: -30, bottom: -34 }} />
                      )}
                    </>
                  }
                >
                  <div style={{ position: "absolute", inset: 0, opacity: exposed }}>
                    <MiniScreen
                      screen={st.screen}
                      k={1}
                      typed={st.screen === "type" ? tw(frame, s0 + 6, 22, (v) => v) : 1}
                      tap={st.screen === "click" ? interpolate(frame, [s0 + 10, s0 + 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0}
                      arrive={st.screen === "list" ? tw(frame, s0 + 4, 12) : 1}
                      reload={st.screen === "reload" ? tw(frame, s0 + 2, 16) : 1}
                    />
                  </div>
                </FilmFrame>
              );
            })}
          </div>
        </FilmBase>
      </div>

      {/* After the pull back: the count, in plain words */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 780,
          textAlign: "center",
          ...text,
          fontSize: 44,
          color: C.muted,
          opacity: tw(frame, PULL + 24, 14),
        }}
      >
        Six steps, six screenshots. Five passed, one failed.
      </div>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: SAFE.y + 40,
          textAlign: "center",
          ...display,
          fontSize: 96,
          color: C.ink,
          opacity: tw(frame, PULL + 16, 12),
          translate: `0 ${lerp(16, 0, tw(frame, PULL + 16, 12))}px`,
        }}
      >
        Every step leaves proof.
      </div>
    </AbsoluteFill>
  );
};
