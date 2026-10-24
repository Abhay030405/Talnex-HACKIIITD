import { describe, expect, it } from "vitest";

import { canUploadResume, isFinishedStatus, stageLabel, stageState } from "@/lib/progress-format";

describe("stage words", () => {
  it("names every stage the API sends", () => {
    const stages = [
      "resume_read",
      "github_profile",
      "codeforces",
      "codechef",
      "leetcode",
      "candidate_report",
      "resume_cleanup",
      "precheck",
      "claims",
      "github_check",
      "test_plan",
      "live_test",
      "proof_check",
      "feature_score",
      "originality",
      "project_summary",
    ];
    for (const s of stages) expect(stageLabel(s)).not.toMatch(/_/);
  });

  it("makes a stage it does not know readable", () => {
    expect(stageLabel("sandbox_run")).toBe("Sandbox run");
  });

  it("says a failed stage could not finish, never that the candidate failed", () => {
    expect(stageState("failed")).toEqual({ text: "Could not finish", tone: "danger" });
    expect(stageState("retrying").text).toBe("Trying again");
    expect(stageState("something_new").text).toBe("Waiting");
  });
});

describe("candidate status", () => {
  it("stops refreshing only when nothing more will happen", () => {
    for (const s of ["done", "done_with_gaps", "failed"]) expect(isFinishedStatus(s)).toBe(true);
    for (const s of ["submitted", "reading", "awaiting_confirmation", "testing"])
      expect(isFinishedStatus(s)).toBe(false);
  });

  it("offers a new resume only when none is being read", () => {
    expect(canUploadResume("done")).toBe(true);
    expect(canUploadResume("reading")).toBe(false);
    expect(canUploadResume("testing")).toBe(false);
  });
});
