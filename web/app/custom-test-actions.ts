"use server";

import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";

/** Run one test the reviewer described, on a resume project or a hackathon project, then watch it live. */
export async function startCustomTestAction(
  target: { kind: "candidate_project" | "project"; id: string },
  instruction: string,
  liveHref: string,
): Promise<{ error?: string }> {
  const base = target.kind === "project" ? "/v1/projects" : "/v1/candidate-projects";
  try {
    await apiFetch(`${base}/${encodeURIComponent(target.id)}/custom-test`, { method: "POST", body: { instruction } });
  } catch (error) {
    return { error: error instanceof ApiError && error.status < 500 ? error.message : "We could not start the test." };
  }
  redirect(liveHref);
}
