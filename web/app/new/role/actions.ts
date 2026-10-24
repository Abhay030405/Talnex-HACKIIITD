"use server";

import { ApiError, apiFetch } from "@/lib/api";
import { MAX_LABEL_LENGTH, resumeProblem } from "@/lib/resume";
import { parseRoleForm } from "@/lib/role-form";
import type { CandidateSummary, JobRole } from "@/lib/types";

export type Result<T> = { ok: true; value: T } | { ok: false; error: string };

const UPLOAD_TIMEOUT_MS = 60_000;

function problem(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.status < 500 ? error.message : fallback;
}

/** Step 1: save the role (job description, person, skills, criteria, checks). The resumes follow one by one. */
export async function createRole(form: FormData): Promise<Result<string>> {
  const parsed = parseRoleForm(form);
  if (!parsed.ok) return parsed;
  try {
    const role = await apiFetch<JobRole>("/v1/roles", { method: "POST", body: parsed.value });
    return { ok: true, value: role.id };
  } catch (error) {
    return { ok: false, error: problem(error, "We could not save the role. Please try again.") };
  }
}

/** Step 2, once per resume: a candidate under the role, then its resume. Small requests, so any number of resumes fit. */
export async function addResume(roleId: string, form: FormData): Promise<Result<string>> {
  const resume = form.get("resume");
  const bad = await resumeProblem(resume);
  if (bad) return { ok: false, error: bad };
  const label = String(form.get("label") ?? "").trim().slice(0, MAX_LABEL_LENGTH);
  let created: CandidateSummary;
  try {
    created = await apiFetch<CandidateSummary>("/v1/candidates", { method: "POST", body: { label, role_id: roleId } });
  } catch (error) {
    return { ok: false, error: problem(error, "We could not save this candidate.") };
  }
  const upload = new FormData();
  upload.set("resume", resume as Blob, "resume.pdf");
  try {
    await apiFetch(`/v1/candidates/${created.id}/resume`, { method: "POST", form: upload, timeoutMs: UPLOAD_TIMEOUT_MS });
  } catch (error) {
    return { ok: false, error: problem(error, "The candidate was saved but the resume did not upload.") };
  }
  return { ok: true, value: created.id };
}
