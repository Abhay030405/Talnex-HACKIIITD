import { describe, expect, it } from "vitest";

import { weightedScore } from "@/lib/role-score";
import type { CandidateReport } from "@/lib/types";

const report = (overalls: (number | null)[]) =>
  ({
    projects: overalls.map((overall, i) => ({
      id: `p${i}`,
      features: [{ group: "Core", score10: 8 }],
      engineering: overall === null ? null : { overall, areas: [] },
    })),
  }) as unknown as CandidateReport;

describe("an Engineering criterion", () => {
  it("weighs the repository engineering quality, averaged over projects", () => {
    const { score, parts } = weightedScore(report([6, 4]), [
      { name: "Core", weight: 1 },
      { name: "Engineering", weight: 1 },
    ]);
    expect(parts[1]).toMatchObject({ name: "Engineering", average: 5, features: 2 });
    expect(score).toBe(6.5);
  });

  it("is left out when no project was judged, like any unscored criterion", () => {
    const { score, parts } = weightedScore(report([null]), [
      { name: "Core", weight: 1 },
      { name: "engineering", weight: 3 },
    ]);
    expect(parts[1].average).toBeNull();
    expect(score).toBe(8);
  });
});
