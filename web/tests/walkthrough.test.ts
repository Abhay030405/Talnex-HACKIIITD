import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  MAX_QUESTION_CHARS,
  choiceQuestion,
  cleanQuestion,
  isFinished,
  isSubject,
  missingStatusWords,
  pickRecordingType,
  refInfo,
  walkthroughsPath,
} from "@/lib/walkthrough-format";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));

const route = await import("@/app/api/walkthroughs/route");
const one = await import("@/app/api/walkthroughs/[walkthroughId]/route");

beforeEach(() => apiFetch.mockReset());

describe("walkthrough helpers", () => {
  it("knows the two kinds of project and their API paths", () => {
    expect(isSubject("project")).toBe(true);
    expect(isSubject("candidate")).toBe(false);
    expect(walkthroughsPath("project", "p 1")).toBe("/v1/projects/p%201/walkthroughs");
    expect(walkthroughsPath("candidate_project", "c1")).toBe("/v1/candidate-projects/c1/walkthroughs");
  });

  it("keeps questions within the API's limit", () => {
    expect(cleanQuestion("  How does login work?  ")).toBe("How does login work?");
    expect(cleanQuestion("x".repeat(MAX_QUESTION_CHARS + 50))).toHaveLength(MAX_QUESTION_CHARS);
    expect(cleanQuestion(42)).toBe("");
  });

  it("records in a format the browser has, including Safari's", () => {
    expect(pickRecordingType((t) => t === "audio/mp4")).toBe("audio/mp4");
    expect(pickRecordingType((t) => t !== "audio/mp4")).toBe("audio/webm");
    expect(pickRecordingType(() => false)).toBeNull();
    expect(pickRecordingType(undefined)).toBeNull();
  });

  it("links code and screenshots, and names the rest", () => {
    expect(refInfo({ kind: "code", path: "a.ts", start: 1, end: 9, commit_sha: "x", url: "https://gh/a" })).toEqual({
      label: "a.ts, lines 1–9",
      url: "https://gh/a",
    });
    expect(refInfo({ kind: "screenshot", view_url: "https://files/s.png" }).url).toBe("https://files/s.png");
    expect(refInfo({ kind: "screenshot" }).url).toBeNull();
    expect(refInfo({ kind: "review", note: "No retry" })).toEqual({
      label: "Code review note",
      url: null,
      note: "No retry",
    });
  });

  it("words the rest", () => {
    expect(isFinished("answering")).toBe(false);
    expect(isFinished("failed")).toBe(true);
    expect(missingStatusWords("not_found_in_code")).toBe("Not found in the code");
    expect(choiceQuestion("Share a chat")).toBe("Walk me through: Share a chat");
  });
});

describe("the website's walkthrough routes", () => {
  const post = (fields: Record<string, string | Blob>) => {
    const form = new FormData();
    for (const [k, v] of Object.entries(fields)) form.set(k, v);
    return route.POST(new Request("http://web/api/walkthroughs", { method: "POST", body: form }));
  };

  it("passes a typed question to the API", async () => {
    apiFetch.mockResolvedValueOnce({ id: "w1", status: "queued" });
    const res = await post({ subject: "project", id: "p1", question: " How does login work? " });
    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ id: "w1", status: "queued" });
    expect(apiFetch).toHaveBeenCalledWith("/v1/projects/p1/walkthroughs", {
      method: "POST",
      body: { question: "How does login work?" },
    });
  });

  it("passes a recording as a file", async () => {
    apiFetch.mockResolvedValueOnce({ id: "w2", status: "queued" });
    const res = await post({
      subject: "candidate_project",
      id: "c1",
      audio: new Blob(["voice"], { type: "audio/mp4" }),
    });
    expect(res.status).toBe(202);
    const [path, request] = apiFetch.mock.calls[0];
    expect(path).toBe("/v1/candidate-projects/c1/walkthroughs");
    expect(request.form.get("audio")).toBeInstanceOf(Blob);
  });

  it("refuses an empty question or an unknown project without calling the API", async () => {
    expect((await post({ subject: "project", id: "p1", question: "  " })).status).toBe(400);
    expect((await post({ subject: "admin", id: "p1", question: "hi" })).status).toBe(400);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("passes the API's refusal on in words, like the daily limit", async () => {
    apiFetch.mockRejectedValueOnce(
      new ApiError("the daily limit of questions for this project is reached; try again tomorrow", 429),
    );
    const res = await post({ subject: "project", id: "p1", question: "hi" });
    expect(res.status).toBe(429);
    expect((await res.json()).error).toMatch(/daily limit/);
  });

  it("never shows a raw error", async () => {
    apiFetch.mockRejectedValueOnce(new Error("socket hang up at 10.0.0.3"));
    const res = await post({ subject: "project", id: "p1", question: "hi" });
    expect(res.status).toBe(502);
    expect((await res.json()).error).toBe("Something went wrong. Please try again.");
  });

  it("lists earlier questions and reads one answer", async () => {
    apiFetch.mockResolvedValueOnce([{ id: "w1" }]);
    const list = await route.GET(new Request("http://web/api/walkthroughs?subject=project&id=p1"));
    expect(await list.json()).toEqual([{ id: "w1" }]);
    apiFetch.mockResolvedValueOnce({ id: "w1", status: "done" });
    const single = await one.GET(new Request("http://web/api/walkthroughs/w1"), {
      params: Promise.resolve({ walkthroughId: "w1" }),
    });
    expect(await single.json()).toEqual({ id: "w1", status: "done" });
    expect(apiFetch).toHaveBeenLastCalledWith("/v1/walkthroughs/w1");
  });
});
