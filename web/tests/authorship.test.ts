import { describe, expect, it } from "vitest";

import { sampleReport } from "@/lib/__fixtures__/report.sample";
import {
  accountLabel,
  authorshipView,
  couldNotTraceText,
  fileLabel,
  formatShare,
  whoBuiltWhatRows,
} from "@/lib/authorship-format";
import { flagTypeLabel } from "@/lib/report-format";

const [traced, untraced] = sampleReport.projects[0].features;

describe("authorship of a claim", () => {
  it("says which account wrote it, with links to the exact lines", () => {
    const view = authorshipView(traced.authorship);
    expect(view).toMatchObject({ kind: "traced", candidateShare: "82%" });
    if (view.kind === "traced") {
      expect(view.summary).toMatch(/written by @asha/);
      expect(view.files).toEqual([
        { label: "src/auth/login.ts, lines 12–40", url: expect.stringContaining("#L12-L40") },
      ]);
    }
  });

  it("calls an untraced claim neutral and gives the reason", () => {
    expect(authorshipView(untraced.authorship)).toEqual({
      kind: "not_traced",
      text: "Could not trace who wrote it: the repository history is private",
      files: [],
    });
    expect(couldNotTraceText("")).toBe("Could not trace who wrote it");
  });

  it("shows nothing for a report made before authorship existed", () => {
    expect(authorshipView(undefined)).toEqual({ kind: "none" });
  });

  it("shows a candidate share of zero, which is an answer, not a gap", () => {
    expect(formatShare(0)).toBe("0%");
    expect(formatShare(null)).toBeNull();
    expect(formatShare(1.4)).toBe("100%");
  });

  it("writes line ranges plainly", () => {
    expect(fileLabel({ path: "a.ts", start: 5, end: 5 })).toBe("a.ts, line 5");
    expect(fileLabel({ path: "a.ts", start: 0, end: 0 })).toBe("a.ts");
  });
});

describe("who built what", () => {
  it("lists accounts by name with unlinked authors last, never by how much they wrote", () => {
    const rows = whoBuiltWhatRows([
      { account: "unlinked", features: ["Search"] },
      { account: "zara", features: ["Login"] },
      { account: "Bob", features: ["Upload", "Share"] },
      { account: "carol", features: [] },
    ]);
    expect(rows.map((r) => r.account)).toEqual(["Bob", "zara", "unlinked"]);
    expect(whoBuiltWhatRows(null)).toEqual([]);
  });

  it("names accounts as GitHub accounts, never as people", () => {
    expect(accountLabel("octocat")).toBe("@octocat");
    expect(accountLabel("@octocat")).toBe("@octocat");
    expect(accountLabel("unlinked")).toMatch(/Unlinked author/);
  });

  it("names the authorship flags", () => {
    expect(flagTypeLabel("feature_before_event")).toBe("Feature built before the event");
    expect(flagTypeLabel("claimed_by_other_account")).toMatch(/another account/);
  });
});
