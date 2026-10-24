"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { parseProjectForm } from "@/lib/event-form";

export interface ProjectFormState {
  error?: string;
  /** The team just added, so the form can say so and clear itself. */
  added?: string;
}

/** Adds one team's project to an event; the event page then lists it. */
export async function addProject(
  eventId: string,
  _previous: ProjectFormState,
  formData: FormData,
): Promise<ProjectFormState> {
  const parsed = parseProjectForm(formData);
  if (!parsed.ok) return { error: parsed.error };

  try {
    await apiFetch(`/v1/events/${encodeURIComponent(eventId)}/projects`, { method: "POST", body: parsed.value });
  } catch (error) {
    if (error instanceof ApiError && error.status < 500) return { error: error.message };
    return { error: "We could not add the project. Please try again." };
  }
  revalidatePath(`/events/${eventId}`);
  return { added: parsed.value.team_name };
}

const eventPath = (eventId: string) => `/events/${encodeURIComponent(eventId)}`;

/** Starts the first check of every project not checked yet. Projects already checked keep their results. */
export async function runEventAction(eventId: string): Promise<void> {
  let outcome: string;
  try {
    const result = await apiFetch<{ started: string[]; skipped: string[] }>(
      `/v1/events/${encodeURIComponent(eventId)}/run`,
      { method: "POST" },
    );
    outcome = `started=${result?.started?.length ?? 0}&skipped=${result?.skipped?.length ?? 0}`;
  } catch {
    outcome = "run=failed";
  }
  revalidatePath(eventPath(eventId));
  redirect(`${eventPath(eventId)}?${outcome}`);
}

/** Checks one project again. The API refuses while that project is still being checked. */
export async function runProjectAction(eventId: string, projectId: string): Promise<void> {
  let outcome = "run=started";
  try {
    await apiFetch(`/v1/projects/${encodeURIComponent(projectId)}/run`, { method: "POST" });
  } catch (error) {
    outcome = error instanceof ApiError && error.status === 409 ? "run=busy" : "run=failed";
  }
  revalidatePath(eventPath(eventId));
  redirect(`${eventPath(eventId)}/projects/${encodeURIComponent(projectId)}?${outcome}`);
}
