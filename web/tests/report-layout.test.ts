import { describe, expect, it } from "vitest";

import { layoutPipeline } from "@/lib/pipeline-flow";
import { evidenceFacts, plainValue, type EvidenceFact } from "@/lib/report-format";
import { githubCard, groupByVerdict, projectAuthorship, verdictCounts } from "@/lib/report-layout";
import type { CodingSignal, JobRow, ReportFeature } from "@/lib/types";

const feature = (verdict: string | null, extra: Record<string, unknown> = {}) =>
  ({ claim_id: Math.random().toString(), verdict, ...extra }) as unknown as ReportFeature;

/** Every string a fact list would put on screen. */
const shown = (facts: EvidenceFact[]): string[] =>
  facts.flatMap((f) => [f.label, f.value ?? "", ...(f.table?.columns ?? []), ...(f.table?.rows.flat() ?? []), ...shown(f.rows ?? [])]);

describe("evidenceFacts never shows raw JSON", () => {
  const evidence = {
    account: "octo",
    repos: [
      { repo: "a", commits: 12, busiest_day_share: 0.75, most_on_one_day: true },
      { repo: "b", commits: 3, nested: { x: 1 } },
    ],
    languages: { TypeScript: 4, Go: 1 },
    since: "2021-03-04T10:00:00Z",
    months: [],
    tags: ["dp", "graphs"],
  };
  const facts = evidenceFacts(evidence);

  it("has no JSON in any value", () => {
    for (const text of shown(facts)) {
      expect(text).not.toContain('{"');
      expect(text).not.toContain("[{");
      expect(text).not.toContain("[object Object]");
    }
  });

  it("turns lists of records into a table, objects into rows, and skips empty lists", () => {
    const repos = facts.find((f) => f.label === "Repos");
    expect(repos?.table?.columns).toEqual(["Repo", "Commits", "Busiest day share", "Most on one day", "Nested"]);
    expect(repos?.table?.rows[0]).toEqual(["a", "12", "75%", "yes", "—"]);
    expect(repos?.table?.rows[1][4]).toBe("X: 1");
    expect(facts.find((f) => f.label === "Languages")?.rows).toEqual([
      { label: "TypeScript", value: "4" },
      { label: "Go", value: "1" },
    ]);
    expect(facts.find((f) => f.label === "Months")).toBeUndefined();
    expect(facts.find((f) => f.label === "Since")?.value).toBe("4 Mar 2021");
  });

  it("writes plain values in words", () => {
    expect(plainValue(12345)).toBe("12,345");
    expect(plainValue(0.4, "candidate_share")).toBe("40%");
    expect(plainValue(false)).toBe("no");
    expect(plainValue(null)).toBe("—");
  });
});

describe("report layout", () => {
  const features = [feature("works"), feature("broken"), feature(null), feature("works")];

  it("counts verdicts, treating a missing one as could not test", () => {
    expect(verdictCounts(features)).toMatchObject({ works: 2, broken: 1, could_not_test: 1, partly_works: 0 });
  });

  it("groups worst first and leaves empty groups out", () => {
    expect(groupByVerdict(features).map((g) => g.verdict)).toEqual(["broken", "works", "could_not_test"]);
  });

  it("sums authorship across features as shares", () => {
    const acc = (account: string, lines: number) => ({ account, lines, commits: 1, first_pushed_at: null, last_pushed_at: null });
    const out = projectAuthorship([
      feature("works", { authorship: { accounts: [acc("me", 30), acc("them", 10)] } }),
      feature("works", { authorship: { accounts: [acc("me", 20)] } }),
    ]);
    expect(out.map((a) => [a.account, a.lines, a.commits, a.share])).toEqual([
      ["me", 50, 2, 50 / 60],
      ["them", 10, 1, 10 / 60],
    ]);
  });
});

describe("githubCard", () => {
  const signal = (months: { month: string; commits: number }[]) =>
    ({ site: "github", signal: "github_profile", weight: "not_suspicious", contest: null, evidence: { account: "octo", months } }) as CodingSignal;
  const m = (...commits: number[]) => commits.map((c, i) => ({ month: `2026-0${i + 1}`, commits: c }));

  it("is null without an account", () => {
    expect(githubCard(undefined)).toBeNull();
  });

  it("marks the trend and the last active month", () => {
    expect(githubCard(signal(m(5, 5, 5, 5, 5, 5)))?.trend).toBe("active");
    expect(githubCard(signal(m(10, 10, 10, 1, 1, 1)))?.trend).toBe("slowing");
    const quiet = githubCard(signal(m(4, 2, 0, 0, 0, 0)));
    expect(quiet?.trend).toBe("quiet");
    expect(quiet?.lastActive).toBe("2026-02");
    expect(quiet?.months.map((x) => [x.quiet, x.height])).toEqual([
      [false, 100],
      [false, 50],
      [true, 0],
      [true, 0],
      [true, 0],
      [true, 0],
    ]);
  });
});

describe("layoutPipeline", () => {
  const job = (stage: string, status: string, after: string[], result: Record<string, unknown> | null = null) =>
    ({ stage, status, after_stages: after, result }) as unknown as JobRow;

  it("puts each stage one column after the deepest stage it waits for", () => {
    const rows = [job("a", "done", []), job("b", "done", ["a"], { skipped: true }), job("c", "running", ["a", "b"])];
    const all = [...rows, job("d", "done", ["c"])];
    const { stages, edges } = layoutPipeline(rows, all);
    expect(stages.map((s) => [s.name, s.depth, s.status])).toEqual([
      ["a", 0, "done"],
      ["b", 1, "skipped"],
      ["c", 2, "running"],
      ["d", 3, "waiting"],
    ]);
    expect(edges).toEqual([
      ["a", "b"],
      ["a", "c"],
      ["b", "c"],
      ["c", "d"],
    ]);
  });
});
