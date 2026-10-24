import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TourWorkspace } from "@/components/tour/TourWorkspace";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { getCandidateReport } from "@/lib/report";
import { requireRole } from "@/lib/session";
import { isTourId, tourPath, type Tour } from "@/lib/tour";

export const metadata: Metadata = { title: "Walk-through" };

/** A chat beside a candidate's project: the guide reads the code and shows how a feature was built. */
export default async function CandidateProjectWalkthroughPage({
  params,
  searchParams,
}: {
  params: Promise<{ candidateId: string; projectId: string }>;
  searchParams: Promise<{ tour?: string }>;
}) {
  const { candidateId, projectId } = await params;
  const { tour: tourId } = await searchParams;
  await requireRole("recruiter");
  const report = await getCandidateReport(candidateId);
  const project = report?.projects.find((p) => p.id === projectId);
  if (!project) notFound();

  let initial: Tour | null = null;
  if (isTourId(tourId)) {
    try {
      initial = await apiFetch<Tour>(tourPath(tourId));
    } catch (error) {
      if (!(error instanceof ApiError) || (error.status !== 404 && error.status !== 400)) throw error;
    }
  }

  return (
    <div className="stack">
      <PageHeader
        title={`Walk-through: ${project.name}`}
        lead="Ask how a feature was built. The guide reads the code, explains it step by step, and shows it on the live site."
        back={{ href: `/candidates/${encodeURIComponent(candidateId)}`, label: "Back to the report" }}
      />
      <TourWorkspace
        subject="candidate_project"
        subjectId={project.id}
        parentId={candidateId}
        siteUrl={project.live_url || null}
        hasRepo={!!project.repo_url}
        initial={initial}
      />
    </div>
  );
}
