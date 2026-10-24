// What the resume reader found for a candidate, for the confirm step.
import "server-only";

import { ApiError, apiFetch } from "@/lib/api";
import type { CandidateFound } from "@/lib/types";

/** What was found, or null when the candidate does not exist or is not yours. */
export async function getCandidateFound(id: string): Promise<CandidateFound | null> {
  try {
    return await apiFetch<CandidateFound>(`/v1/candidates/${encodeURIComponent(id)}/found`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
