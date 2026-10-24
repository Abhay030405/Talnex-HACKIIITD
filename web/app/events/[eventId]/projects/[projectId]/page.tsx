import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SubmitButton } from "@/components/forms/SubmitButton";
import { HackathonCardView } from "@/components/proof/HackathonCardView";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { PageHeader } from "@/components/ui/PageHeader";
import { BADGE_CLASS } from "@/lib/format";
import { projectStatus } from "@/lib/hackathon-format";
import { getProject, getProjectCard } from "@/lib/project-card";
import { requireRole } from "@/lib/session";
import { tourPageUrl } from "@/lib/tour";

import { runProjectAction } from "../../actions";

export const metadata: Metadata = { title: "Proof card" };

const RUN_MESSAGES: Record<string, { text: string; good: boolean }> = {
  started: { text: "The check has started. This page updates by itself.", good: true },
  busy: { text: "This project is still being checked. Wait for it to finish.", good: false },
  failed: { text: "The check could not be started. Please try again.", good: false },
};

export default async function ProjectPage({
  params,
  searchParams,
}: {
  params: Promise<{ eventId: string; projectId: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { eventId, projectId } = await params;
  const { run } = await searchParams;
  await requireRole("organizer");

  const project = await getProject(projectId);
  if (!project || project.event_id !== eventId) notFound();
  const card = await getProjectCard(projectId);
  const status = projectStatus(project.status);
  const message = run ? RUN_MESSAGES[run] : undefined;

  return (
    <div className="stack">
      <AutoRefresh active={status.running} />

      <PageHeader
        title={project.team_name}
        back={{ href: `/events/${encodeURIComponent(eventId)}`, label: "Back to the event" }}
        actions={
          <>
            <Link
              href={`/events/${encodeURIComponent(eventId)}/projects/${encodeURIComponent(projectId)}/live`}
              className="button button--ghost"
            >
              Watch live
            </Link>
            {!status.running && (
              <form action={runProjectAction.bind(null, eventId, projectId)}>
                <SubmitButton pendingText="Starting…">{card ? "Check again" : "Check this project"}</SubmitButton>
              </form>
            )}
          </>
        }
      >
        <div className="row">
          <span className={BADGE_CLASS[status.tone]}>{status.text}</span>
        </div>
      </PageHeader>

      {message && (
        <p className={message.good ? "form-success" : "form-error"} role="status">
          {message.text}
        </p>
      )}

      {card ? (
        <HackathonCardView card={card} tourHref={tourPageUrl("project", projectId, eventId)} />
      ) : (
        <section className="panel" aria-labelledby="pending-title">
          <div className="panel__head">
            <h2 className="panel__title" id="pending-title">
              Proof card
            </h2>
          </div>
          <div className="panel__body">
            <p className="note">
              {status.running
                ? `${project.status_detail || status.text}. The proof card appears here when the check is done.`
                : "This project has not been checked yet. Start a check above."}
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
