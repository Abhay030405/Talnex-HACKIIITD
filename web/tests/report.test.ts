import { describe, expect, it } from "vitest";

import { sampleReport } from "@/lib/__fixtures__/report.sample";
import {
  confidenceLabel,
  evidenceFacts,
  flagLevelInfo,
  flagTypeLabel,
  formatCoverage,
  formatScore,
  projectStatusInfo,
  proofInfo,
  reportSummary,
  scoreLevel,
  signalWeightInfo,
  sortFlags,
  statusWords,
  verdictInfo,
} from "@/lib/report-format";
import type { Verdict } from "@/lib/types";

describe("verdicts", () => {
  it("never shows could-not-test as a failure", () => {
    expect(verdictInfo("could_not_test")).toEqual({ text: "Could not test", tone: "neutral" });
    expect(verdictInfo(null)).toEqual({ text: "Not tested", tone: "neutral" });
  });

  it("always labels code that was only read", () => {
    expect(verdictInfo("reviewed_from_code").text).toBe("Reviewed from code, not run");
  });

  it("names every verdict the database allows", () => {
    for (const v of ["works", "partly_works", "broken", "could_not_test", "reviewed_from_code"] as Verdict[]) {
      expect(verdictInfo(v).text).not.toBe("Not tested");
    }
  });

  it("asks for a human when two checks disagree", () => {
    expect(confidenceLabel("disagree")).toMatch(/human/);
    expect(confidenceLabel(null)).toBe("");
  });
});

describe("scores", () => {
  it("colours by level at the edges", () => {
    expect([10, 7, 6.9, 4, 3.9, 0].map(scoreLevel)).toEqual(["high", "high", "medium", "medium", "low", "low"]);
  });

  it("writes scores and coverage plainly", () => {
    expect(formatScore(8)).toBe("8");
    expect(formatScore(6.25)).toBe("6.3");
    expect(formatScore(null)).toBe("–");
    expect(formatCoverage(74.6)).toBe("75%");
    expect(formatCoverage(140)).toBe("100%");
  });
});

describe("flags", () => {
  it("puts the strongest first and keeps the rest in order", () => {
    const sorted = sortFlags(sampleReport.projects[0].flags);
    expect(sorted.map((f) => f.level)).toEqual(["strong", "info"]);
    expect(sampleReport.projects[0].flags[0].level).toBe("info");
  });

  it("names levels and types in words, even ones it does not know", () => {
    expect(flagLevelInfo("strong")).toEqual({ text: "Strong signal", tone: "danger" });
    expect(flagTypeLabel("hidden_ai_instructions")).toMatch(/Hidden instructions/);
    expect(flagTypeLabel("brand_new_check")).toBe("Brand new check");
  });
});

describe("proof", () => {
  const steps = sampleReport.projects[0].features[0].proof;

  it("shows screenshots as pictures and backend proof as links, never a broken picture", () => {
    expect(steps.map((s) => proofInfo(s).show)).toEqual(["image", "link", "link", "none"]);
    expect(proofInfo(steps[1]).text).toMatch(/request and answer/);
    expect(proofInfo(steps[2]).text).toMatch(/command output/);
  });
});

describe("the whole report", () => {
  it("counts tested projects and scored features, leaving untestable ones out", () => {
    expect(reportSummary(sampleReport)).toEqual({
      projectsTested: 1,
      projectsTotal: 2,
      featuresScored: 4,
      featuresTotal: 6,
    });
  });

  it("says why a project was not tested, without blame", () => {
    expect(projectStatusInfo("no_live_link")).toEqual({ text: "No live link", tone: "neutral" });
  });

  it("reads coding signals with the weights the database allows", () => {
    expect(signalWeightInfo("not_suspicious").text).toBe("Not suspicious");
    expect(signalWeightInfo("medium").text).toBe("Worth a look");
    expect(signalWeightInfo("strong").tone).toBe("danger");
  });

  it("turns evidence into short labelled facts", () => {
    expect(evidenceFacts({ rating_change: 410, solved_fast: true, empty: "", tags: ["dp", "graphs"] })).toEqual([
      { label: "Rating change", value: "410" },
      { label: "Solved fast", value: "yes" },
      { label: "Tags", value: "dp, graphs" },
    ]);
  });

  it("explains every candidate status in words", () => {
    for (const s of [
      "submitted",
      "reading",
      "prechecking",
      "testing",
      "reporting",
      "done",
      "done_with_gaps",
      "failed",
    ]) {
      expect(statusWords(s)).not.toBe("Working on it.");
    }
  });
});
