// How far a candidate's check has got.
import "server-only";

import { ApiError, apiFetch } from "@/lib/api";
import type { CandidateProgress } from "@/lib/types";

/** The progress, or null when the candidate does not exist or is not yours. */
export async function getCandidateProgress(id: string): Promise<CandidateProgress | null> {
  try {
    return await apiFetch<CandidateProgress>(`/v1/candidates/${encodeURIComponent(id)}/progress`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
