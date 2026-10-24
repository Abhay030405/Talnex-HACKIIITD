import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TourWorkspace } from "@/components/tour/TourWorkspace";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { getProject } from "@/lib/project-card";
import { requireRole } from "@/lib/session";
import { isTourId, tourPath, type Tour } from "@/lib/tour";

export const metadata: Metadata = { title: "Walk-through" };

/** A chat beside the team's live site: the guide reads the code and shows how a feature was built. */
export default async function ProjectWalkthroughPage({
  params,
  searchParams,
}: {
  params: Promise<{ eventId: string; projectId: string }>;
  searchParams: Promise<{ tour?: string }>;
}) {
  const { eventId, projectId } = await params;
  const { tour: tourId } = await searchParams;
  await requireRole("organizer");
  const project = await getProject(projectId);
  if (!project || project.event_id !== eventId) notFound();

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
        title={`Walk-through: ${project.team_name}`}
        lead="Ask how a feature was built. The guide reads the code, explains it step by step, and shows it on the live site."
        back={{
          href: `/events/${encodeURIComponent(eventId)}/projects/${encodeURIComponent(projectId)}`,
          label: "Back to the proof card",
        }}
      />
      <TourWorkspace
        subject="project"
        subjectId={project.id}
        parentId={eventId}
        siteUrl={project.live_url || null}
        hasRepo={!!project.repo_url}
        initial={initial}
      />
    </div>
  );
}
