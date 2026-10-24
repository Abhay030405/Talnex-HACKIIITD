import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { MAX_RESUME_BYTES, resumeProblem } from "@/lib/resume";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw Object.assign(new Error("NEXT_REDIRECT"), { to });
  },
}));

const { createCandidate } = await import("@/app/new/recruiter/actions");

const pdf = (extra = "") => new File([`%PDF-1.7\n${extra}`], "resume.pdf", { type: "application/pdf" });
const form = (fields: Record<string, string | File>) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
};
const redirectOf = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e: { to?: string }) => e.to ?? e,
  );

beforeEach(() => apiFetch.mockReset());

describe("resume file rules", () => {
  it("takes a real PDF", async () => {
    expect(await resumeProblem(pdf())).toBeNull();
  });

  it("refuses no file, an empty file, a big file and a renamed non-PDF", async () => {
    expect(await resumeProblem(null)).toMatch(/choose/);
    expect(await resumeProblem(new File([], "a.pdf"))).toMatch(/choose/);
    expect(await resumeProblem(new File([new Uint8Array(MAX_RESUME_BYTES + 1)], "big.pdf"))).toMatch(/5 MB/);
    expect(await resumeProblem(new File(["PK\u0003\u0004 docx inside"], "resume.pdf"))).toMatch(/must be a PDF/);
  });
});

describe("creating a candidate", () => {
  it("saves the candidate, uploads the resume, then opens the candidate", async () => {
    apiFetch.mockResolvedValueOnce({ id: "c1" }).mockResolvedValueOnce({ candidate_id: "c1", run: 1 });
    const to = await redirectOf(createCandidate({}, form({ resume: pdf(), role_level: "junior", label: "  Asha  " })));
    expect(to).toBe("/candidates/c1");
    expect(apiFetch.mock.calls[0]).toEqual([
      "/v1/candidates",
      { method: "POST", body: { label: "Asha", role_level: "junior" } },
    ]);
    const [path, request] = apiFetch.mock.calls[1];
    expect(path).toBe("/v1/candidates/c1/resume");
    expect(request.form.get("resume")).toBeInstanceOf(Blob);
    expect(request.timeoutMs).toBeGreaterThan(20_000);
  });

  it("saves nothing when the file is wrong", async () => {
    expect(await createCandidate({}, form({ resume: new File(["hello"], "a.pdf"), role_level: "junior" }))).toEqual({
      error: expect.stringMatching(/must be a PDF/),
    });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("saves nothing without a real role level", async () => {
    expect(await createCandidate({}, form({ resume: pdf(), role_level: "boss" }))).toEqual({
      error: "Please pick a role level.",
    });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows the API's reason when it refuses the candidate", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("role_level must be fresher, junior, mid or senior", 400));
    expect(await createCandidate({}, form({ resume: pdf(), role_level: "mid" }))).toEqual({
      error: "role_level must be fresher, junior, mid or senior",
    });
  });

  it("keeps the person on the form with plain words when the API breaks", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("internal", 500));
    expect(await createCandidate({}, form({ resume: pdf(), role_level: "mid" }))).toEqual({
      error: "We could not save the candidate. Please try again.",
    });
  });

  it("still opens the saved candidate, marked, when only the upload fails", async () => {
    apiFetch.mockResolvedValueOnce({ id: "c2" }).mockRejectedValueOnce(new ApiError("slow", 504));
    expect(await redirectOf(createCandidate({}, form({ resume: pdf(), role_level: "mid" })))).toBe(
      "/candidates/c2?resume=failed",
    );
  });
});
