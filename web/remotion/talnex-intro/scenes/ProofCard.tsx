import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Circle } from "../components/Marker";
import { Verdict, VerdictKind, verdictColor } from "../components/Verdict";
import { C, display, lerp, text, tw } from "../theme";

export const PROOF_DURATION = 230;

const ROWS: { claim: string; reason: string; score: string; kind: VerdictKind; note?: string }[] = [
  {
    claim: "Upload an image and get a caption",
    reason: "Worked with 3 different images.",
    score: "8",
    kind: "works",
  },
  {
    claim: "Search past captions",
    reason: "Every search returns a server error.",
    score: "0",
    kind: "broken",
    note: "Failed 3 times and a second check agreed.",
  },
  {
    claim: "Share a caption by link",
    reason: "The link opens, but the image is missing.",
    score: "5",
    kind: "partly",
  },
  {
    claim: "Sign in with a phone code",
    reason: "The code never arrived.",
    score: "–",
    kind: "untested",
    note: "Left out of the score. It never counts against anyone.",
  },
];

const Row: React.FC<{ row: (typeof ROWS)[number]; at: number; noteAt: number; first: boolean }> = ({
  row,
  at,
  noteAt,
  first,
}) => {
  const frame = useCurrentFrame();
  const t = tw(frame, at, 12);
  const n = tw(frame, noteAt, 14);
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 70px 290px 420px",
        alignItems: "center",
        gap: 40,
        padding: "20px 48px",
        borderTop: first ? "none" : `2px solid ${C.lineSoft}`,
        opacity: t,
        translate: `0 ${lerp(18, 0, t)}px`,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ ...text, fontWeight: 500, fontSize: 36, color: C.ink }}>{row.claim}</span>
        <span style={{ ...text, fontSize: 27, color: C.faint }}>{row.reason}</span>
      </div>
      <span style={{ ...display, fontSize: 64, color: verdictColor(row.kind), textAlign: "right" }}>{row.score}</span>
      <span>
        <Verdict kind={row.kind} size={28} />
      </span>
      {row.note ? (
        <span
          style={{
            ...text,
            fontWeight: 500,
            fontSize: 26,
            lineHeight: 1.35,
            color: C.marker,
            paddingLeft: 18,
            borderLeft: `5px solid ${C.marker}`,
            opacity: n,
            clipPath: `inset(0 ${100 - 100 * n}% 0 0)`,
          }}
        >
          {row.note}
        </span>
      ) : (
        <span />
      )}
    </div>
  );
};

export const ProofCard: React.FC = () => {
  const frame = useCurrentFrame();
  const rise = interpolate(frame, [0, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.2, 0, 0, 1),
  });
  const score = lerp(0, 4.3, tw(frame, 26, 44));
  const push = tw(frame, 30, PROOF_DURATION - 30, (v) => v);
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <div
        style={{
          position: "absolute",
          left: 150,
          right: 150,
          top: 112,
          background: C.raised,
          border: `2px solid ${C.line}`,
          borderRadius: 24,
          translate: `0 ${lerp(900, 0, rise)}px`,
          scale: String(lerp(1, 1.02, push)),
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            padding: "34px 48px 28px",
            borderBottom: `2px solid ${C.line}`,
          }}
        >
          <div>
            <div style={{ ...display, fontSize: 92, color: C.ink }}>CaptionBuddy</div>
            <div style={{ ...text, fontSize: 30, color: C.faint, marginTop: 12 }}>
              3 of 4 features tested. 26 screenshots.
            </div>
          </div>
          <div style={{ position: "relative", display: "flex", alignItems: "baseline", gap: 16 }}>
            <span style={{ ...display, fontSize: 150, color: C.ink, minWidth: 170, textAlign: "right", opacity: tw(frame, 26, 6) }}>
              {score.toFixed(1)}
            </span>
            <span style={{ ...text, fontSize: 32, color: C.faint }}>out of 10</span>
            <Circle progress={tw(frame, 150, 18)} w={440} h={250} style={{ left: -44, top: -62 }} />
          </div>
        </div>
        {ROWS.map((row, i) => (
          <Row key={row.claim} row={row} at={20 + i * 10} noteAt={96 + (i === 3 ? 22 : 0)} first={i === 0} />
        ))}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            padding: "22px 48px",
            borderTop: `2px solid ${C.line}`,
            background: C.surface,
            borderRadius: "0 0 24px 24px",
            ...text,
            fontSize: 28,
            color: C.muted,
            opacity: tw(frame, 128, 14),
          }}
        >
          Red flags sit beside the score. They are never taken off it. There is no ranking.
        </div>
      </div>
    </AbsoluteFill>
  );
};
