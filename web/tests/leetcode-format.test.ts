import { describe, expect, it } from "vitest";

import { pasteCard, replaySummary } from "@/lib/leetcode-format";
import { weightedFromGroups } from "@/lib/role-score";
import type { CodingSignal } from "@/lib/types";

const paste: CodingSignal = {
  site: "leetcode",
  signal: "leetcode_paste",
  weight: "medium",
  contest: "weekly-contest-524",
  problem: "Last Visited Cell",
  evidence: {
    at: "04:13", lines: 25, edits_after: 0, idle_before_s: 253, rating_jump: 420,
    same_code: { compared: 3, matches: 0, best_pct: 57.1 }, reason: "core logic pasted in one go",
    snippet: "m, n := len(grid)", ranking_url: "https://leetcode.com/contest/weekly-contest-524/ranking/",
  },
};

describe("leetcode paste card", () => {
  it("says what was pasted, when, and how it compares", () => {
    const card = pasteCard(paste);
    expect(card?.title).toBe("weekly-contest-524 · Last Visited Cell");
    expect(card?.lines).toEqual([
      "Pasted 25 lines at 04:13, 0 edits after",
      "Editor quiet for 253s just before",
      "+420 rating that contest",
      "Same code as 0 of 3 nearby contestants (closest 57.1%)",
    ]);
    expect(card?.linkText).toBe("Open the contest ranking (replay at 04:13)");
  });

  it("leaves out small jumps and short idles, and shows a could-not-check reason", () => {
    const card = pasteCard({
      ...paste,
      evidence: { ...paste.evidence, idle_before_s: 5, rating_jump: 20, same_code: { reason: "could not check: 403" } },
    });
    expect(card?.lines).toEqual(["Pasted 25 lines at 04:13, 0 edits after", "could not check: 403"]);
  });

  it("only handles its own signals", () => {
    expect(pasteCard({ ...paste, signal: "leetcode_profile" })).toBeNull();
    expect(replaySummary(paste)).toBeNull();
    expect(
      replaySummary({ ...paste, signal: "leetcode_replay", evidence: { contests_checked: ["a", "b"], replays_read: 7, pastes: 3, suspicious_pastes: 1 } }),
    ).toBe("Code Replay: 2 contests and 7 problem replays read, 3 pastes, 1 worth a look.");
  });
});

describe("hackathon overview total", () => {
  it("uses the current weights like the proof card", () => {
    const groups = [{ group: "Core", score: 80 }, { group: "UI", score: 40 }];
    expect(weightedFromGroups(groups, [{ name: "Core", weight: 3 }, { name: "UI", weight: 1 }]).score).toBe(70);
    expect(weightedFromGroups(groups, [{ name: "Core", weight: 1 }, { name: "UI", weight: 3 }]).score).toBe(50);
  });
});
