"use server";

import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { MAX_LABEL_LENGTH, resumeProblem } from "@/lib/resume";
import { ROLE_CHECKS, ROLE_LEVELS, type CandidateSummary, type JobRole } from "@/lib/types";

export interface FormState {
  error?: string;
}

/** A resume upload on a slow connection can take a while; the default 20 seconds is too short. */
const UPLOAD_TIMEOUT_MS = 60_000;

/** Step 1: save the candidate with the role level, then send the resume. Step 2 is the confirm page. */
export async function createCandidate(_previous: FormState, formData: FormData): Promise<FormState> {
  const text = (name: string) => String(formData.get(name) ?? "").trim();

  const resume = formData.get("resume");
  const problem = await resumeProblem(resume);
  if (problem) return { error: problem };

  const roleLevel = text("role_level");
  if (!ROLE_LEVELS.some((r) => r.value === roleLevel)) return { error: "Please pick a role level." };

  // A partial check: the checks live on a role, so a small role is saved for this one resume. The full check needs none.
  const shown = formData.has("checks_shown");
  const chosen = new Set(shown ? formData.getAll("checks").map(String) : ROLE_CHECKS.map((c) => c.value));
  if (chosen.size === 0) return { error: "Choose at least one check to run." };
  let roleId = "";
  if (ROLE_CHECKS.some((c) => !chosen.has(c.value))) {
    try {
      const role = await apiFetch<JobRole>("/v1/roles", {
        method: "POST",
        body: {
          title: `Quick check: ${text("label") || "one resume"}`.slice(0, 120),
          role_level: roleLevel,
          checks: Object.fromEntries(ROLE_CHECKS.map((c) => [c.value, chosen.has(c.value)])),
          auto_confirm: false,
        },
      });
      roleId = role.id;
    } catch (error) {
      if (error instanceof ApiError && error.status < 500) return { error: error.message };
      return { error: "We could not save the chosen checks. Please try again." };
    }
  }

  let created: CandidateSummary;
  try {
    created = await apiFetch<CandidateSummary>("/v1/candidates", {
      method: "POST",
      body: { label: text("label").slice(0, MAX_LABEL_LENGTH), role_level: roleLevel, ...(roleId ? { role_id: roleId } : {}) },
    });
  } catch (error) {
    if (error instanceof ApiError && error.status < 500) return { error: error.message };
    return { error: "We could not save the candidate. Please try again." };
  }

  const upload = new FormData();
  upload.set("resume", resume as Blob, "resume.pdf");
  let uploaded = true;
  try {
    await apiFetch(`/v1/candidates/${created.id}/resume`, {
      method: "POST",
      form: upload,
      timeoutMs: UPLOAD_TIMEOUT_MS,
    });
  } catch {
    uploaded = false;
  }
  // Outside the try: redirect works by throwing, and a catch would swallow it.
  redirect(uploaded ? `/candidates/${created.id}` : `/candidates/${created.id}?resume=failed`);
}
