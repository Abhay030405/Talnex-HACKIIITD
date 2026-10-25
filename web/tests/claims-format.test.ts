import { describe, expect, it } from "vitest";

import { claimsTimeline } from "@/lib/claims-format";

const actual = (first: string, last: string) => ({
  repo: "a/b", commit_count: 3, first_commit: first, last_commit: last, contributors: [],
});

describe("resume vs GitHub timeline", () => {
  it("puts both ranges on one axis in tenths", () => {
    const line = claimsTimeline({ start: "2026-01", end: "2026-10" }, actual("2026-01-05T00:00:00Z", "2026-05-30T00:00:00Z"));
    expect(line).toEqual({ claimed: [0, 10], actual: [0, 5], from: "2026-01", to: "2026-10" });
  });

  it("shows commits that come before the claimed dates", () => {
    const line = claimsTimeline({ start: "2026", end: "2026" }, actual("2025-01-01T00:00:00Z", "2025-12-31T00:00:00Z"));
    expect(line?.actual[0]).toBe(0);
    expect(line?.claimed[0]).toBe(5);
  });

  it("draws nothing without both ranges", () => {
    expect(claimsTimeline({}, actual("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"))).toBeNull();
    expect(claimsTimeline({ start: "2026-01" }, null)).toBeNull();
  });
});
