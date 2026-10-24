// A verdict is always a word, a glyph and a colour together.
import { CSSProperties } from "react";
import { C, text } from "../theme";

export type VerdictKind = "works" | "partly" | "broken" | "untested";

const V: Record<VerdictKind, { word: string; color: string; soft: string; line: string }> = {
  works: { word: "Works", color: C.works, soft: C.worksSoft, line: C.worksLine },
  partly: { word: "Partly works", color: C.partly, soft: C.partlySoft, line: C.partlyLine },
  broken: { word: "Broken", color: C.broken, soft: C.brokenSoft, line: C.brokenLine },
  untested: { word: "Could not test", color: C.untested, soft: "transparent", line: C.lineStrong },
};

export const verdictColor = (k: VerdictKind) => V[k].color;

export const Glyph: React.FC<{ kind: VerdictKind; size: number; color?: string }> = ({ kind, size, color }) => {
  const stroke = color ?? V[kind].color;
  const common = {
    fill: "none",
    stroke,
    strokeWidth: 2.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ flex: "none" }}>
      {kind === "works" && <path d="M20 6 9 17l-5-5" {...common} />}
      {kind === "broken" && <path d="M18 6 6 18M6 6l12 12" {...common} />}
      {kind === "partly" && (
        <>
          <circle cx="12" cy="12" r="9" {...common} />
          <path d="M12 3a9 9 0 0 1 0 18z" fill={stroke} />
        </>
      )}
      {kind === "untested" && <circle cx="12" cy="12" r="9" {...common} strokeDasharray="3.2 3" />}
    </svg>
  );
};

export const Verdict: React.FC<{ kind: VerdictKind; size?: number; style?: CSSProperties; label?: string }> = ({
  kind,
  size = 26,
  style,
  label,
}) => {
  const v = V[kind];
  return (
    <span
      style={{
        ...text,
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.35,
        padding: `${size * 0.22}px ${size * 0.6}px`,
        border: `2px ${kind === "untested" ? "dashed" : "solid"} ${v.line}`,
        borderRadius: 999,
        background: v.soft,
        color: v.color,
        fontSize: size,
        fontWeight: 600,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      <Glyph kind={kind} size={size * 0.95} />
      {label ?? v.word}
    </span>
  );
};
