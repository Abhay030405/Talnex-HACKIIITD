import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { MAX_PROJECTS, parseConfirmForm, profileValue } from "@/lib/confirm-format";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw Object.assign(new Error("NEXT_REDIRECT"), { to });
  },
}));

const { confirmAction } = await import("@/app/candidates/[candidateId]/actions");

const form = (fields: Record<string, string>) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
};

beforeEach(() => apiFetch.mockReset());

describe("parseConfirmForm", () => {
  it("keeps rows in order, skips empty and removed rows, and sends every coding site", () => {
    const parsed = parseConfirmForm(
      form({
        "project.0.id": "p1",
        "project.0.name": "  Chat   app ",
        "project.0.live_url": " https://chat.example ",
        "project.5.name": "Blog",
        "project.5.repo_url": "github.com/a/blog",
        "project.3.name": "",
        "project.3.id": "p9",
        "profile.leetcode": " asha ",
        unrelated: "x",
      }),
    );
    expect(parsed).toEqual({
      ok: true,
      value: {
        projects: [
          { id: "p1", name: "Chat app", live_url: "https://chat.example", repo_url: "", video_url: "" },
          { name: "Blog", live_url: "", repo_url: "github.com/a/blog", video_url: "" },
        ],
        coding_profiles: { codeforces: "", leetcode: "asha", codechef: "" },
      },
    });
  });

  it.each([
    [{}, /at least one project/],
    [{ "project.0.live_url": "https://x.example" }, /needs a name/],
    [{ "project.0.name": "Chat", "project.1.name": "chat" }, /Two projects are called/],
    [{ "project.0.name": "x".repeat(121) }, /too long/],
    [
      Object.fromEntries(Array.from({ length: MAX_PROJECTS + 1 }, (_, i) => [`project.${i}.name`, `P${i}`])),
      /at most 8/,
    ],
  ])("explains what the API would refuse: %j", (fields, words) => {
    const parsed = parseConfirmForm(form(fields as Record<string, string>));
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.error).toMatch(words);
  });

  it("fills a profile box with the resume's link, else the handle", () => {
    expect(profileValue("leetcode", { leetcode: "https://leetcode.com/u/asha" }, { leetcode: "asha" })).toBe(
      "https://leetcode.com/u/asha",
    );
    expect(profileValue("codechef", {}, { codechef: "asha_cc" })).toBe("asha_cc");
    expect(profileValue("codeforces", {}, {})).toBe("");
  });
});

describe("confirmAction", () => {
  const good = form({ "project.0.name": "Chat app", "project.0.live_url": "https://chat.example" });

  it("starts the checks and opens the candidate", async () => {
    apiFetch.mockResolvedValueOnce({});
    const to = await confirmAction("c 1", {}, good).catch((e) => e.to);
    expect(to).toBe("/candidates/c%201");
    expect(apiFetch).toHaveBeenCalledWith("/v1/candidates/c%201/confirm", {
      method: "POST",
      body: expect.objectContaining({ projects: [expect.objectContaining({ name: "Chat app" })] }),
    });
  });

  it("sends nothing when the form is wrong", async () => {
    expect(await confirmAction("c1", {}, form({}))).toEqual({ error: "Add at least one project to check." });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows the API's reason, like a link it cannot use", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("Chat app: the live link is not a web address", 400));
    expect(await confirmAction("c1", {}, good)).toEqual({ error: "Chat app: the live link is not a web address" });
  });

  it("opens the candidate when it was already confirmed elsewhere", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("this check is not waiting for confirmation", 409));
    expect(await confirmAction("c1", {}, good).catch((e) => e.to)).toBe("/candidates/c1");
  });

  it("keeps the recruiter on the form with plain words when the API breaks", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("boom", 500));
    expect(await confirmAction("c1", {}, good)).toEqual({ error: "We could not start the checks. Please try again." });
  });
});
