"use server";

import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";

const problem = (error: unknown, fallback: string) =>
  error instanceof ApiError && error.status < 500 ? error.message : fallback;

/** Run the chosen stages of one pipeline again for one target, then watch it live. */
export async function runStagesAction(path: string, stages: string[], liveHref: string): Promise<{ error?: string }> {
  try {
    await apiFetch(path, { method: "POST", body: { stages } });
  } catch (error) {
    return { error: problem(error, "We could not start those stages.") };
  }
  redirect(liveHref);
}

/** Put one failed job back in the queue, in its own run. */
export async function retryJobAction(jobId: string, liveHref: string): Promise<{ error?: string }> {
  try {
    await apiFetch(`/v1/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
  } catch (error) {
    return { error: problem(error, "We could not retry that job.") };
  }
  redirect(liveHref);
}
