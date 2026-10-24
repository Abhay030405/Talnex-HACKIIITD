"use server";

import { revalidatePath } from "next/cache";

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
