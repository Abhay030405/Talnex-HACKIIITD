// A candidate's proof report.
import "server-only";

import { ApiError, apiFetch } from "@/lib/api";
import type { CandidateReport } from "@/lib/types";

/** The report, or null while it is not ready yet (the API answers 404 until then). */
export async function getCandidateReport(id: string): Promise<CandidateReport | null> {
  try {
    return await apiFetch<CandidateReport>(`/v1/candidates/${encodeURIComponent(id)}/report`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
