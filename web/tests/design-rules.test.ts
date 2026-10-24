// Keeps AGENTS.md sections 5 and 6 true for the website: design values live only in app/globals.css,
// and settings are read only in lib/env.ts.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
const SOURCE_DIRS = ["app", "components", "lib"];
const SKIP = new Set(["node_modules", ".next", "tests"]);

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((entry) => {
    if (SKIP.has(entry)) return [];
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

const files = [...SOURCE_DIRS.map((d) => join(ROOT, d)).flatMap(sourceFiles), join(ROOT, "auth.ts")].filter(existsSync);
const read = (file: string) => readFileSync(file, "utf8");
const short = (file: string) => relative(ROOT, file).split(sep).join("/");
const offending = (test: (text: string) => boolean) => files.filter((f) => test(read(f))).map(short);

const css = read(join(ROOT, "app/globals.css"));
const tokenBlock = /:root\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
const outsideTokens = css.replace(/:root\s*\{[^}]*\}/, "").replace(/\/\*[\s\S]*?\*\//g, "");

describe("components", () => {
  it("finds the source files", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("use no inline styles", () => {
    // The one exception: React Flow gives the docs' orchestration diagram its node sizes and label positions at run
    // time, so that file may set them inline. Colours, fonts and spacing there still come from globals.css.
    const geometry = new Set(["components/docs/diagrams/orchestration-flow.tsx"]);
    const styled = offending((t) => /\sstyle=\{|\sstyle="/.test(t)).filter((f) => !geometry.has(f));
    expect(styled).toEqual([]);
  });

  it("type no colour codes", () => {
    expect(offending((t) => /["'`]#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(t))).toEqual([]);
  });

  it("type no font names or pixel sizes", () => {
    expect(offending((t) => /fontFamily|font-family|\b\d+px\b/.test(t))).toEqual([]);
  });

  it("only use class names the stylesheet defines", () => {
    const used = new Set<string>();
    for (const file of files) {
      for (const match of read(file).matchAll(/className=(?:"([^"]+)"|\{`([^`]+)`\})/g)) {
        const value = (match[1] ?? match[2]).replace(/\$\{[^}]*\}/g, " ");
        value.split(/\s+/).filter(Boolean).forEach((c) => used.add(c));
      }
    }
    // A class ending in "--" is a prefix finished at run time, like "score-chip--" + level.
    // "not-prose" is fumadocs' own switch that keeps its prose styles off a block (the docs diagrams); it has no rule.
    const vendor = new Set(["not-prose"]);
    const missing = [...used].filter((c) => !c.endsWith("--") && !vendor.has(c) && !new RegExp(`\\.${c}(?![\\w-])`).test(css));
    expect(missing).toEqual([]);
  });
});

describe("stylesheet", () => {
  it("keeps colour codes inside the token block", () => {
    expect(outsideTokens.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g) ?? []).toEqual([]);
  });

  it("defines every token it uses", () => {
    // The font variables are set on <html> by the self-hosted fonts (app/layout.tsx), not in the stylesheet.
    const fromFonts = ["--font-geist-sans", "--font-geist-mono", "--font-archivo"];
    const defined = new Set([...tokenBlock.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]).concat(fromFonts));
    const used = new Set([...css.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]));
    expect([...used].filter((t) => !defined.has(t))).toEqual([]);
  });
});

describe("settings", () => {
  it("are read from process.env only in lib/env.ts", () => {
    const offenders = files.filter((f) => short(f) !== "lib/env.ts" && /process\.env/.test(read(f))).map(short);
    expect(offenders).toEqual([]);
  });

  it("never go behind NEXT_PUBLIC_, which reaches the browser", () => {
    expect(offending((t) => /NEXT_PUBLIC_/.test(t))).toEqual([]);
  });
});
