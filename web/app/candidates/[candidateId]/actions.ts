"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { parseConfirmForm } from "@/lib/confirm-format";
import { resumeProblem } from "@/lib/resume";

export interface ConfirmState {
  error?: string;
}

const candidatePath = (id: string) => `/candidates/${encodeURIComponent(id)}`;
const UPLOAD_TIMEOUT_MS = 60_000;

/** Sends the confirmed projects and coding profiles. The checks start as soon as the API accepts them. */
export async function confirmAction(
  candidateId: string,
  _previous: ConfirmState,
  formData: FormData,
): Promise<ConfirmState> {
  const parsed = parseConfirmForm(formData);
  if (!parsed.ok) return { error: parsed.error };

  try {
    await apiFetch(`/v1/candidates/${encodeURIComponent(candidateId)}/confirm`, { method: "POST", body: parsed.value });
  } catch (error) {
    // 409: it was already confirmed, maybe in another tab. The candidate page shows where it is.
    if (!(error instanceof ApiError && error.status === 409)) {
      if (error instanceof ApiError && error.status < 500) return { error: error.message };
      return { error: "We could not start the checks. Please try again." };
    }
  }
  redirect(candidatePath(candidateId));
}

/** Sends a new resume for an existing candidate, then shows the candidate again with how it went. */
export async function uploadResumeAction(candidateId: string, formData: FormData): Promise<void> {
  const resume = formData.get("resume");
  const problem = await resumeProblem(resume);
  let outcome = problem ? "invalid" : "";
  if (!problem) {
    const upload = new FormData();
    upload.set("resume", resume as Blob, "resume.pdf");
    try {
      await apiFetch(`/v1/candidates/${encodeURIComponent(candidateId)}/resume`, {
        method: "POST",
        form: upload,
        timeoutMs: UPLOAD_TIMEOUT_MS,
      });
    } catch (error) {
      outcome = error instanceof ApiError && error.status === 409 ? "busy" : "failed";
    }
  }
  redirect(outcome ? `${candidatePath(candidateId)}?resume=${outcome}` : candidatePath(candidateId));
}

/** Deletes the candidate with every result and stored file. The API refuses while a check is running. */
export async function deleteCandidateAction(candidateId: string): Promise<void> {
  let outcome = "";
  try {
    await apiFetch(`/v1/candidates/${encodeURIComponent(candidateId)}`, { method: "DELETE" });
  } catch (error) {
    outcome = error instanceof ApiError && error.status === 409 ? "busy" : "failed";
  }
  redirect(outcome ? `${candidatePath(candidateId)}/delete?error=${outcome}` : "/recruiter");
}

/** Test one resume project again, or read the coding profiles again; then watch it live. */
export async function rerunAction(candidateId: string, what: { kind: "project"; projectId: string } | { kind: "coding" }) {
  const path =
    what.kind === "project"
      ? `/v1/candidate-projects/${encodeURIComponent(what.projectId)}/rerun`
      : `/v1/candidates/${encodeURIComponent(candidateId)}/rerun-coding`;
  try {
    await apiFetch(path, { method: "POST" });
  } catch (error) {
    return { error: error instanceof ApiError && error.status < 500 ? error.message : "We could not start it. Try again." };
  }
  redirect(`${candidatePath(candidateId)}/live`);
}

/** Ask TalNex one question about this candidate's report; the answer appears on the page when ready. */
export async function askAction(candidateId: string, _previous: { error?: string }, form: FormData) {
  const question = String(form.get("question") ?? "").trim();
  if (!question) return { error: "Type a question first." };
  try {
    await apiFetch(`/v1/candidates/${encodeURIComponent(candidateId)}/ask`, { method: "POST", body: { question } });
  } catch (error) {
    return { error: error instanceof ApiError && error.status < 500 ? error.message : "We could not send the question." };
  }
  revalidatePath(candidatePath(candidateId));
  return {};
}
