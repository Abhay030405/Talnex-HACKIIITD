import { describe, expect, it } from "vitest";

import { weightedFromGroups } from "@/lib/role-score";

describe("hackathon weighted total from current weights", () => {
  const groups = [
    { group: "Core flow", score: 80 },
    { group: "Design", score: 40 },
    { group: "Docs", score: null },
  ];

  it("re-scores at once when a weight changes", () => {
    expect(weightedFromGroups(groups, [{ name: "Core flow", weight: 1 }, { name: "Design", weight: 1 }]).score).toBe(60);
    expect(weightedFromGroups(groups, [{ name: "core flow", weight: 3 }, { name: "Design", weight: 1 }]).score).toBe(70);
  });

  it("leaves unscored criteria out and says how much weight counted", () => {
    const t = weightedFromGroups(groups, [{ name: "Core flow", weight: 1 }, { name: "Docs", weight: 1 }]);
    expect(t).toEqual({ score: 80, weight_covered: 50, criteria_used: 1, criteria_total: 2 });
    expect(weightedFromGroups(groups, [{ name: "Docs", weight: 2 }]).score).toBeNull();
  });
});
