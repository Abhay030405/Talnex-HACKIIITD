"use server";

import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { parseEventForm } from "@/lib/event-form";
import type { EventSummary } from "@/lib/types";

export interface FormState {
  error?: string;
}

export async function createEvent(_previous: FormState, formData: FormData): Promise<FormState> {
  const parsed = parseEventForm(formData);
  if (!parsed.ok) return { error: parsed.error };

  let created: EventSummary;
  try {
    created = await apiFetch<EventSummary>("/v1/events", { method: "POST", body: parsed.value });
  } catch (error) {
    if (error instanceof ApiError && error.status < 500) return { error: error.message };
    return { error: "We could not save the event. Please try again." };
  }
  redirect(`/events/${created.id}`);
}
