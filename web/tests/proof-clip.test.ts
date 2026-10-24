import { describe, expect, it } from "vitest";

import { proofClip } from "@/lib/report-format";
import type { ProofStep } from "@/lib/types";

const shot = (step: number, action: string, url?: string): ProofStep => ({
  step,
  action,
  observed: step === 3 ? "milk is listed" : null,
  kind: "screen",
  proof_url: url,
});

describe("proof clip", () => {
  it("plays the screenshots in order and ends on the verdict", () => {
    const clip = proofClip(
      [shot(1, "Open the page", "u1"), shot(2, 'Type "TalNex test milk"', "u2"), shot(3, "Final check", "u3")],
      "works",
    );
    expect(clip?.frames.map((f) => f.url)).toEqual(["u1", "u2", "u3"]);
    expect(clip?.frames[1].caption).toBe('Step 2: Type "TalNex test milk"');
    expect(clip?.frames[2].seen).toBe("milk is listed");
    expect(clip?.stamp).toEqual({ text: "Works", tone: "success" });
  });

  it("skips steps without a screenshot, like a backend request or a missing file", () => {
    const http: ProofStep = { step: 2, action: "GET /api", observed: null, kind: "http", proof_url: "h" };
    const clip = proofClip([shot(1, "a", "u1"), http, shot(3, "b"), shot(4, "c", "u4")], "broken");
    expect(clip?.frames.map((f) => f.url)).toEqual(["u1", "u4"]);
    expect(clip?.stamp.tone).toBe("danger");
  });

  it("has nothing to play with fewer than two screenshots", () => {
    expect(proofClip([shot(1, "a", "u1")], "works")).toBeNull();
    expect(proofClip([], null)).toBeNull();
  });

  it("never stamps could-not-test as a failure", () => {
    const clip = proofClip([shot(1, "a", "u1"), shot(2, "b", "u2")], "could_not_test");
    expect(clip?.stamp).toEqual({ text: "Could not test", tone: "neutral" });
  });
});
