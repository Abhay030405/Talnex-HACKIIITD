import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw Object.assign(new Error("NEXT_REDIRECT"), { to });
  },
}));

const { deleteCandidateAction, uploadResumeAction } = await import("@/app/candidates/[candidateId]/actions");

const withFile = (file: File) => {
  const f = new FormData();
  f.set("resume", file);
  return f;
};
const pdf = new File(["%PDF-1.7\n"], "cv.pdf", { type: "application/pdf" });
const to = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e: { to?: string }) => e.to,
  );

beforeEach(() => apiFetch.mockReset());

describe("checking again with a new resume", () => {
  it("uploads and shows the candidate", async () => {
    apiFetch.mockResolvedValueOnce({ run: 2 });
    expect(await to(uploadResumeAction("c1", withFile(pdf)))).toBe("/candidates/c1");
    expect(apiFetch.mock.calls[0][0]).toBe("/v1/candidates/c1/resume");
  });

  it("refuses a file that is not a PDF without calling the API", async () => {
    expect(await to(uploadResumeAction("c1", withFile(new File(["hello"], "cv.pdf"))))).toBe(
      "/candidates/c1?resume=invalid",
    );
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("says when a resume is still being read, or the upload failed", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("this resume is still being read", 409));
    expect(await to(uploadResumeAction("c1", withFile(pdf)))).toBe("/candidates/c1?resume=busy");
    apiFetch.mockRejectedValueOnce(new ApiError("boom", 500));
    expect(await to(uploadResumeAction("c1", withFile(pdf)))).toBe("/candidates/c1?resume=failed");
  });
});

describe("deleting a check", () => {
  it("deletes and goes back to the list", async () => {
    apiFetch.mockResolvedValueOnce(null);
    expect(await to(deleteCandidateAction("c1"))).toBe("/recruiter");
    expect(apiFetch).toHaveBeenCalledWith("/v1/candidates/c1", { method: "DELETE" });
  });

  it("stays on the delete page with the reason when it cannot", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("this check is still running; wait for it to finish", 409));
    expect(await to(deleteCandidateAction("c1"))).toBe("/candidates/c1/delete?error=busy");
  });
});
