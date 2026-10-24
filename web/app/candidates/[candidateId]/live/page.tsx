import type { Metadata } from "next";
import { notFound, unstable_rethrow } from "next/navigation";

import { LiveView } from "@/components/live/LiveView";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { getCandidateProgress } from "@/lib/progress";
import { requireRole } from "@/lib/session";
import type { CandidateSummary } from "@/lib/types";

export const metadata: Metadata = { title: "Watch live" };

/** A candidate's check, live: the resume and one panel per project on it. */
export default async function CandidateLivePage({ params }: { params: Promise<{ candidateId: string }> }) {
  const { candidateId } = await params;
  await requireRole("recruiter");

  let candidate: CandidateSummary;
  try {
    candidate = await apiFetch<CandidateSummary>(`/v1/candidates/${encodeURIComponent(candidateId)}`);
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) notFound();
    throw error;
  }
  const label = candidate.label || "Unnamed candidate";
  const names: Record<string, string> = { [candidateId]: `${label} (resume and profiles)` };
  try {
    for (const p of (await getCandidateProgress(candidateId))?.projects ?? []) names[p.id] = p.name;
  } catch (error) {
    unstable_rethrow(error); // without names the panels still show, labelled by kind
  }

  return (
    <div className="stack">
      <PageHeader
        title={`Live: ${label}`}
        lead="What TalNex is doing right now, project by project. Click a project to see it full size."
        back={{ href: `/candidates/${encodeURIComponent(candidateId)}`, label: "Back to the candidate" }}
      />
      <LiveView kind="candidate" id={candidateId} names={names} />
    </div>
  );
}
