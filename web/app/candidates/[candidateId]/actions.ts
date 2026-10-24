"use server";

import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { parseConfirmForm } from "@/lib/confirm-format";

export interface ConfirmState {
  error?: string;
}

const candidatePath = (id: string) => `/candidates/${encodeURIComponent(id)}`;

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

