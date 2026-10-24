import { Check, CircleDashed, Code2, Contrast, Flag, Loader, X, type LucideIcon } from "lucide-react";

export type VerdictKind = "works" | "partly" | "broken" | "untested" | "testing" | "code" | "flag";

const VERDICTS: Record<VerdictKind, { word: string; Icon: LucideIcon }> = {
  works: { word: "Works", Icon: Check },
  partly: { word: "Partly works", Icon: Contrast },
  broken: { word: "Broken", Icon: X },
  // Could not test is calm and neutral: a dashed outline, never a warning colour. It never counts against anyone.
  untested: { word: "Could not test", Icon: CircleDashed },
  testing: { word: "Testing", Icon: Loader },
  code: { word: "From code", Icon: Code2 },
  flag: { word: "Flag", Icon: Flag },
};

/** A verdict as the design system shows it: always a word, a glyph and a colour together, never colour alone. */
export function VerdictBadge({ kind, children }: { kind: VerdictKind; children?: React.ReactNode }) {
  const { word, Icon } = VERDICTS[kind];
  return (
    <span className={`verdict verdict--${kind}`}>
      <Icon size={12} strokeWidth={2.25} aria-hidden="true" />
      {children ?? word}
    </span>
  );
}
