import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LiveView } from "@/components/live/LiveView";
import { PageHeader } from "@/components/ui/PageHeader";
import { getEventOverview } from "@/lib/project-card";
import { requireRole } from "@/lib/session";

export const metadata: Metadata = { title: "Watch live" };

/** Every team of the event being checked, live: one panel per team. */
export default async function EventLivePage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  await requireRole("organizer");
  const overview = await getEventOverview(eventId);
  if (!overview) notFound();
  const { event, projects } = overview;
  const names: Record<string, string> = { [event.id]: `${event.name} (whole event)` };
  for (const p of projects) names[p.id] = p.team_name;

  return (
    <div className="stack">
      <PageHeader
        title={`Live: ${event.name}`}
        lead="What TalNex is doing right now, team by team. Click a team to see it full size."
        back={{ href: `/events/${encodeURIComponent(event.id)}`, label: "Back to the event" }}
      />
      <LiveView kind="event" id={event.id} names={names} />
    </div>
  );
}
