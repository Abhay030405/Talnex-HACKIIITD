import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  anyRunning,
  flagCountText,
  groupKindLabel,
  linksGiven,
  projectStatus,
  runAllText,
} from "@/lib/hackathon-format";

const { apiFetch, revalidatePath } = vi.hoisted(() => ({ apiFetch: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));
vi.mock("next/cache", () => ({ revalidatePath }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw Object.assign(new Error("NEXT_REDIRECT"), { to });
  },
}));

const { runEventAction, runProjectAction } = await import("@/app/events/[eventId]/actions");
const to = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e: { to?: string }) => e.to,
  );

beforeEach(() => {
  apiFetch.mockReset();
  revalidatePath.mockReset();
});

describe("project status", () => {
  it("names every status a hackathon project can carry", () => {
    for (const s of [
      "submitted",
      "prechecking",
      "reading",
      "testing",
      "checking",
      "scoring",
      "done",
      "done_with_gaps",
    ]) {
      expect(projectStatus(s).text).not.toBe("In progress");
    }
  });

  it("knows which statuses are still running, to keep the page fresh", () => {
    expect(anyRunning([{ status: "done" }, { status: "testing" }])).toBe(true);
    expect(anyRunning([{ status: "done" }, { status: "submitted" }, { status: "failed" }])).toBe(false);
    expect(projectStatus("brand_new").running).toBe(true);
  });
});

describe("words on the organizer pages", () => {
  it("counts flags without ever mixing them into a score", () => {
    expect(flagCountText({ strong: 1, review: 2 })).toBe("1 strong · 2 to look at");
    expect(flagCountText({})).toBe("None");
  });

  it("names group kinds and the links a team gave", () => {
    expect(groupKindLabel("criterion")).toBe("Your criterion");
    expect(linksGiven({ has_live: true, has_repo: true, has_video: false })).toBe("live site, repository");
    expect(linksGiven({ has_live: false, has_repo: false, has_video: false })).toBe("no links");
  });

  it("says what happened after checking all projects", () => {
    expect(runAllText(2, 1)).toBe("2 projects started, 1 already checked or being checked.");
    expect(runAllText(1, 0)).toBe("1 project started.");
    expect(runAllText(0, 0)).toMatch(/no projects/);
  });
});

describe("running checks", () => {
  it("starts every new project and reports the counts", async () => {
    apiFetch.mockResolvedValueOnce({ started: ["p1", "p2"], skipped: ["p3"] });
    expect(await to(runEventAction("e1"))).toBe("/events/e1?started=2&skipped=1");
    expect(apiFetch).toHaveBeenCalledWith("/v1/events/e1/run", { method: "POST" });
    expect(revalidatePath).toHaveBeenCalledWith("/events/e1");
  });

  it("says when the event run could not start", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("boom", 500));
    expect(await to(runEventAction("e1"))).toBe("/events/e1?run=failed");
  });

  it("checks one project again, or says it is still running", async () => {
    apiFetch.mockResolvedValueOnce({ project_id: "p1", run: 2 });
    expect(await to(runProjectAction("e1", "p1"))).toBe("/events/e1/projects/p1?run=started");
    apiFetch.mockRejectedValueOnce(new ApiError("this project is still being checked", 409));
    expect(await to(runProjectAction("e1", "p1"))).toBe("/events/e1/projects/p1?run=busy");
  });
});
