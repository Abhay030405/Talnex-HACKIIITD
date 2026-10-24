import { describe, expect, it } from "vitest";

import { networkSummary } from "@/lib/network";
import type { ProofStep } from "@/lib/types";

const step = (devtools: ProofStep["devtools"]): ProofStep => ({ step: 1, action: "a", observed: null, kind: "screen", devtools });

describe("network summary", () => {
  it("sums API calls, latency, errors, console errors and leaks over every step", () => {
    const summary = networkSummary([
      {
        proof: [
          step({ api_calls: [{ method: "GET", url: "/a", status: 200, ms: 100 }, { method: "POST", url: "/b", status: 500, ms: 2500 }],
                 error_responses: [{ method: "POST", url: "/b", status: 500 }], console_errors: ["[error] boom"] }),
          step(null),
        ],
      },
      { proof: [step({ api_calls: [{ method: "GET", url: "/c", status: 200 }], failed_requests: [{ method: "GET", url: "/d", error: "net" }],
                       page_errors: ["x"], leaks: [{ type: "jwt", level: "review", masked: "eyJh••••abcd", where: "console" }] })] },
    ]);
    expect(summary).toEqual({ apiCalls: 3, averageMs: 1300, slowestMs: 2500, errors: 2, consoleErrors: 2, leaks: 1 });
  });

  it("is empty when nothing was recorded", () => {
    expect(networkSummary([{ proof: [step(null)] }])).toBeNull();
  });
});
