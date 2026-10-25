// The film strip: base, sprocket holes, frames with a tiny screenshot inside, and amber edge numbering.
import { CSSProperties, ReactNode } from "react";
import { C, display, mono, text } from "../theme";

export type Screen = "load" | "type" | "click" | "list" | "error" | "reload";

export const STEPS: { screen: Screen; caption: string; passed: boolean }[] = [
  { screen: "load", caption: "Open the site", passed: true },
  { screen: "type", caption: "Type an item", passed: true },
  { screen: "click", caption: "Click Add", passed: true },
  { screen: "list", caption: "Item is in the list", passed: true },
  { screen: "error", caption: "Search “milk”", passed: false },
  { screen: "reload", caption: "Reload, still there", passed: true },
];

/** A row of paper-coloured holes punched along the film edge. */
export const Holes: React.FC<{ width: number; k?: number; offset?: number }> = ({ width, k = 1, offset = 0 }) => {
  const pitch = 44 * k;
  const hole = 20 * k;
  const count = Math.ceil(width / pitch) + 2;
  return (
    <div style={{ position: "relative", height: hole * 0.8, width, overflow: "hidden" }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: i * pitch + (offset % pitch) - pitch / 2,
            top: 0,
            width: hole,
            height: hole * 0.8,
            borderRadius: 3 * k,
            background: C.filmHole,
            opacity: 0.92,
          }}
        />
      ))}
    </div>
  );
};

type MiniProps = {
  screen: Screen;
  k: number;
  /** 0..1 how much of "Milk" is typed (type step). */
  typed?: number;
  /** 0..1 tap ripple (click step). */
  tap?: number;
  /** 0..1 new item arriving (list step). */
  arrive?: number;
  /** 0..1 page reload flash. */
  reload?: number;
};

/** A tiny screenshot of the todo app at one step, drawn in plain blocks so it reads at thumbnail size. */
export const MiniScreen: React.FC<MiniProps> = ({ screen, k, typed = 1, tap = 0, arrive = 1, reload = 1 }) => {
  const box: CSSProperties = {
    position: "absolute",
    inset: 8 * k,
    borderRadius: 6 * k,
    background: C.mockBg,
    color: C.ink,
    overflow: "hidden",
    ...text,
    fontSize: 24 * k,
    lineHeight: 1.3,
  };
  if (screen === "error") {
    return (
      <div style={{ ...box, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10 * k }}>
        <span style={{ ...display, fontSize: 120 * k }}>500</span>
        <span style={{ color: C.faint, fontSize: 26 * k }}>Internal server error</span>
      </div>
    );
  }
  const hasTyped = screen !== "load";
  const added = screen === "list" || screen === "reload";
  const word = "Milk".slice(0, Math.round(typed * 4));
  const item: CSSProperties = {
    padding: `${6 * k}px ${14 * k}px`,
    borderBottom: `${2 * k}px solid ${C.mockLineSoft}`,
  };
  return (
    <div style={{ ...box, padding: `${20 * k}px ${26 * k}px`, display: "flex", flexDirection: "column", gap: 10 * k, opacity: screen === "reload" ? 0.35 + 0.65 * reload : 1 }}>
      <span style={{ ...display, fontSize: 40 * k }}>Todos</span>
      <div style={{ display: "flex", gap: 10 * k }}>
        <div
          style={{
            flex: 1,
            height: 48 * k,
            boxSizing: "border-box",
            padding: `${8 * k}px ${14 * k}px`,
            border: `${2 * k}px solid ${hasTyped && !added ? C.testing : C.mockLine}`,
            borderRadius: 6 * k,
            background: C.mockSurface,
          }}
        >
          {hasTyped && !added ? word : ""}
          {screen === "type" && typed < 1 ? <span style={{ color: C.testing }}>|</span> : null}
        </div>
        <div
          style={{
            position: "relative",
            display: "grid",
            placeItems: "center",
            padding: `0 ${20 * k}px`,
            borderRadius: 6 * k,
            background: C.ink,
            color: C.mockSurface,
            fontWeight: 600,
          }}
        >
          Add
          {screen === "click" && tap > 0 && tap < 1 ? (
            <div
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: 90 * k,
                height: 90 * k,
                marginLeft: -45 * k,
                marginTop: -45 * k,
                borderRadius: "50%",
                border: `${4 * k}px solid ${C.testing}`,
                scale: String(0.3 + 0.7 * tap),
                opacity: 1 - tap,
              }}
            />
          ) : null}
        </div>
      </div>
      {added ? (
        <div
          style={{
            ...item,
            borderLeft: `${5 * k}px solid ${C.works}`,
            background: C.worksSoft,
            opacity: arrive,
            translate: `0 ${(1 - arrive) * -14 * k}px`,
          }}
        >
          Milk
        </div>
      ) : null}
      <div style={item}>Bread</div>
      <div style={item}>Call the bank</div>
    </div>
  );
};

/** One frame on the strip: the dark frame holding a screenshot, then the edge printing under it. */
export const FilmFrame: React.FC<{
  index: number;
  caption: string;
  width: number;
  k: number;
  children: ReactNode;
  overlay?: ReactNode;
}> = ({ index, caption, width, k, children, overlay }) => (
  <div style={{ width, display: "flex", flexDirection: "column", gap: 16 * k, flex: "none" }}>
    <div style={{ position: "relative", width, height: width * 0.75, borderRadius: 6 * k, background: C.filmFrame }}>
      {children}
      {overlay}
    </div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 16 * k, color: C.filmEdge, whiteSpace: "nowrap" }}>
      <span style={{ ...mono, fontWeight: 600, fontSize: 28 * k }}>{String(index + 1).padStart(2, "0")}</span>
      <span style={{ ...text, fontSize: 28 * k, fontWeight: 500 }}>{caption}</span>
    </div>
  </div>
);

/** The film base with holes along both edges. Children are the frames. */
export const FilmBase: React.FC<{ width: number; k?: number; children: ReactNode; style?: CSSProperties; holeOffset?: number }> = ({
  width,
  k = 1,
  children,
  style,
  holeOffset = 0,
}) => (
  <div
    style={{
      width,
      background: C.film,
      display: "flex",
      flexDirection: "column",
      gap: 22 * k,
      padding: `${16 * k}px 0`,
      ...style,
    }}
  >
    <Holes width={width} k={k} offset={holeOffset} />
    {children}
    <Holes width={width} k={k} offset={holeOffset} />
  </div>
);
