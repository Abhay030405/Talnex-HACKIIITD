import { describe, expect, it } from "vitest";

import { BADGE_CLASS, candidateStatus, countByStage, formatDate, formatDateRange } from "@/lib/format";

describe("dates", () => {
  it("shows a date in UTC, so a late-evening event does not slip a day", () => {
    expect(formatDate("2026-11-04T23:30:00Z")).toBe("4 Nov 2026");
    expect(formatDate("not a date")).toBe("—");
  });

  it("shortens a range inside one month and spells out longer ones", () => {
    expect(formatDateRange("2026-11-04T00:00:00Z", "2026-11-06T23:59:59Z")).toBe("4 – 6 Nov 2026");
    expect(formatDateRange("2026-11-04T00:00:00Z", "2026-11-04T23:59:59Z")).toBe("4 Nov 2026");
    expect(formatDateRange("2026-11-30T00:00:00Z", "2026-12-02T23:59:59Z")).toBe("30 Nov 2026 – 2 Dec 2026");
    expect(formatDateRange("2026-12-31T00:00:00Z", "2027-01-01T23:59:59Z")).toBe("31 Dec 2026 – 1 Jan 2027");
  });
});

describe("candidate status", () => {
  it("names every status the backend and workers set", () => {
    const statuses = [
      "submitted",
      "reading",
      "awaiting_confirmation",
      "prechecking",
      "testing",
      "reporting",
      "done",
      "done_with_gaps",
      "failed",
    ];
    for (const s of statuses) expect(candidateStatus(s).text).not.toBe("In progress");
  });

  it("marks a check that waits for the recruiter as theirs to act on", () => {
    expect(candidateStatus("awaiting_confirmation")).toMatchObject({ text: "Needs your check", stage: "needs_you" });
  });

  it("shows a status it does not know as work in progress", () => {
    expect(candidateStatus("something_new")).toEqual({ text: "In progress", tone: "warning", stage: "working" });
  });

  it("counts candidates by what they need", () => {
    const counts = countByStage(
      ["awaiting_confirmation", "testing", "reading", "done", "done_with_gaps", "failed", "new_one"].map((status) => ({
        status,
      })),
    );
    expect(counts).toEqual({ needs_you: 1, working: 3, finished: 2, failed: 1 });
  });

  it("has a badge style for every tone", () => {
    for (const cls of Object.values(BADGE_CLASS)) expect(cls).toMatch(/^badge/);
  });
});

describe("time and cost of a check", () => {
  it("says time the way a person would and keeps tiny costs visible", async () => {
    const { formatDuration, formatCost, runLine } = await import("@/lib/format");
    expect(formatDuration(42)).toBe("42 s");
    expect(formatDuration(281)).toBe("4 min 41 s");
    expect(formatDuration(240)).toBe("4 min");
    expect(formatDuration(3780)).toBe("1 h 3 min");
    expect(formatCost(0.1412)).toBe("$0.14");
    expect(formatCost(0.0026)).toBe("$0.0026");
    expect(formatCost(0)).toBe("$0.00");
    expect(runLine({ seconds: 281, finished: true, cost_usd: 0.14, model_usd: 0.09, browser_usd: 0.05 })).toBe(
      "Checked in 4 min 41 s · $0.14 (model $0.09 · browser $0.05)",
    );
    expect(runLine({ seconds: 30, finished: false, cost_usd: 0.004, model_usd: 0.004, browser_usd: 0 })).toBe(
      "Running for 30 s · $0.0040 (model $0.0040 · browser $0.00)",
    );
  });
});
