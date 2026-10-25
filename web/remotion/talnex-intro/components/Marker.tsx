// China-marker marks, drawn on with stroke-dashoffset (pathLength=1 so 1 is the full stroke).
// Paths are authored in a small design box and scaled to real pixels here, so the stroke keeps its width
// without vector-effect (which breaks pathLength-based dashes in Chrome).
import { CSSProperties } from "react";
import { C, MARKER_WIDTH } from "../theme";

const scalePath = (d: string, sx: number, sy: number) => {
  let n = 0;
  return d.replace(/-?\d*\.?\d+/g, (num) => {
    const v = parseFloat(num) * (n++ % 2 === 0 ? sx : sy);
    return v.toFixed(2);
  });
};

type MarkProps = {
  progress: number;
  w: number;
  h: number;
  style?: CSSProperties;
  width?: number;
  color?: string;
};

const makeMark =
  (paths: string[], vw: number, vh: number): React.FC<MarkProps> =>
  ({ progress, w, h, style, width = MARKER_WIDTH, color = C.marker }) => {
    const n = paths.length;
    return (
      <svg
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        style={{ position: "absolute", overflow: "visible", pointerEvents: "none", ...style }}
      >
        {paths.map((p, i) => {
          // Multi-stroke marks draw one stroke after the other.
          const local = Math.min(1, Math.max(0, progress * n - i));
          return (
            <path
              key={i}
              d={scalePath(p, w / vw, h / vh)}
              pathLength={1}
              fill="none"
              stroke={color}
              strokeWidth={width}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="1 2"
              strokeDashoffset={1 - local}
              opacity={local > 0 ? 1 : 0}
            />
          );
        })}
      </svg>
    );
  };

export const Circle = makeMark(
  ["M30 40 C 60 8, 180 4, 205 45 C 226 85, 200 148, 112 152 C 30 156, 4 116, 12 76 C 18 46, 52 24, 96 18"],
  220,
  160,
);
export const Tick = makeMark(["M6 28 L 22 44 L 54 6"], 60, 50);
export const Cross = makeMark(["M8 8 L 52 54", "M52 6 L 10 52"], 60, 60);
export const Underline = makeMark(["M2 8 C 80 2, 200 12, 298 4"], 300, 12);
export const Question = makeMark(
  ["M14 22 C 14 8, 26 2, 36 4 C 50 7, 54 22, 44 32 C 36 40, 30 42, 30 56", "M29.5 71 L 30.5 73"],
  60,
  80,
);
