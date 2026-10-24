import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LiveView } from "@/components/live/LiveView";
import { PageHeader } from "@/components/ui/PageHeader";
import { getProject } from "@/lib/project-card";
import { requireRole } from "@/lib/session";

export const metadata: Metadata = { title: "Watch live" };

/** One team's check, live. */
export default async function ProjectLivePage({ params }: { params: Promise<{ eventId: string; projectId: string }> }) {
  const { eventId, projectId } = await params;
  await requireRole("organizer");
  const project = await getProject(projectId);
  if (!project || project.event_id !== eventId) notFound();

  return (
    <div className="stack">
      <PageHeader
        title={`Live: ${project.team_name}`}
        lead="What TalNex is doing right now on this project."
        back={{
          href: `/events/${encodeURIComponent(eventId)}/projects/${encodeURIComponent(projectId)}`,
          label: "Back to the proof card",
        }}
      />
      <LiveView kind="project" id={project.id} names={{ [project.id]: project.team_name }} />
    </div>
  );
}
