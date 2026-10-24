import type { Metadata } from "next";
import Link from "next/link";

import { ArrowIcon, PlusIcon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { BADGE_CLASS, EVENT_STATE_BADGE, formatDateRange } from "@/lib/format";
import { load } from "@/lib/load";
import { requireRole } from "@/lib/session";
import { eventState, modeLabel, roleLabel, type EventState, type EventSummary } from "@/lib/types";

export const metadata: Metadata = { title: "Events" };

export default async function OrganizerWorkspace() {
  const session = await requireRole("organizer");
  const { data, problem } = await load<EventSummary[]>("/v1/events", "your events");
  const events = data ?? [];
  const now = new Date();
  const count = (state: EventState) => events.filter((e) => eventState(e, now) === state).length;
  const name = session.user.name || session.user.email || "there";

  return (
    <div className="stack">
      <PageHeader
        title="Events"
        lead={`Welcome back, ${name}. Check every submission before judging starts.`}
        actions={
          <Link href="/new/hackathon" className="button button--primary">
            <PlusIcon size={16} />
            New event
          </Link>
        }
      />

      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : (
        <>
          <div className="stats">
            <StatTile label="Events" value={events.length} hint="All hackathons you set up" />
            <StatTile label="Live now" value={count("live")} hint="Happening today" />
            <StatTile label="Upcoming" value={count("upcoming")} hint="Not started yet" />
            <StatTile label="Ended" value={count("ended")} hint="Ready to review" />
          </div>

          <section className="panel" aria-labelledby="all-events">
            <div className="panel__head">
              <h2 className="panel__title" id="all-events">
                All events
              </h2>
              <span className="meta">{events.length} total</span>
            </div>
            {events.length === 0 ? (
              <div className="panel__empty">
                <p>No events yet. Set up your first hackathon to start checking submissions.</p>
                <Link href="/new/hackathon" className="button button--soft">
                  <PlusIcon size={16} />
                  Set up an event
                </Link>
              </div>
            ) : (
              <div className="table__wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Event</th>
                      <th scope="col">Type</th>
                      <th scope="col">Judged as</th>
                      <th scope="col">Dates</th>
                      <th scope="col">State</th>
                      <th scope="col">
                        <span className="sr-only">Open</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((event) => {
                      const state = EVENT_STATE_BADGE[eventState(event, now)];
                      const href = `/events/${event.id}`;
                      return (
                        <tr key={event.id}>
                          <td>
                            <Link href={href} className="table__link">
                              {event.name}
                            </Link>
                          </td>
                          <td>{modeLabel(event.mode)}</td>
                          <td>{roleLabel(event.role_level)}</td>
                          <td>{formatDateRange(event.starts_at, event.ends_at)}</td>
                          <td>
                            <span className={BADGE_CLASS[state.tone]}>{state.text}</span>
                          </td>
                          <td className="table__end">
                            <Link href={href} className="table__open" aria-label={`Open ${event.name}`}>
                              <ArrowIcon size={16} />
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
