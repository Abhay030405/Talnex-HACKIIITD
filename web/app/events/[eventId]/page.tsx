import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProjectForm } from "@/components/forms/ProjectForm";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { ArrowIcon } from "@/components/ui/Icons";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { PageHeader } from "@/components/ui/PageHeader";
import { BADGE_CLASS, EVENT_STATE_BADGE, formatDate } from "@/lib/format";
import { anyRunning, flagCountText, linksGiven, projectStatus, runAllText } from "@/lib/hackathon-format";
import { getEventOverview } from "@/lib/project-card";
import { formatCoverage, formatScore } from "@/lib/report-format";
import { requireRole } from "@/lib/session";
import { eventState, modeLabel, roleLabel } from "@/lib/types";

import { runEventAction } from "./actions";

export const metadata: Metadata = { title: "Hackathon check" };

export default async function EventPage({
  params,
  searchParams,
}: {
  params: Promise<{ eventId: string }>;
  searchParams: Promise<{ started?: string; skipped?: string; run?: string }>;
}) {
  const { eventId } = await params;
  const query = await searchParams;
  await requireRole("organizer");

  const overview = await getEventOverview(eventId);
  if (!overview) notFound();
  const { event, projects } = overview;
  const state = EVENT_STATE_BADGE[eventState(event)];
  const path = `/events/${encodeURIComponent(event.id)}`;
  const criteria = event.criteria ?? [];
  const hasResults = projects.some((p) => p.report_ready);

  return (
    <div className="stack">
      <AutoRefresh active={anyRunning(projects)} />

      <PageHeader
        title={event.name}
        back={{ href: "/organizer", label: "All events" }}
        actions={
          hasResults && (
            <Link href={`${path}/compare`} className="button button--soft">
              Who built each feature best <ArrowIcon size={16} />
            </Link>
          )
        }
      >
        <div className="row">
          <span className={BADGE_CLASS[state.tone]}>{state.text}</span>
          <span className="badge badge--neutral">{modeLabel(event.mode)}</span>
          <span className="badge badge--neutral">Judged as {roleLabel(event.role_level)}</span>
        </div>
      </PageHeader>

      {query.started !== undefined && (
        <p className="form-success" role="status">
          {runAllText(Number(query.started) || 0, Number(query.skipped) || 0)}
        </p>
      )}
      {query.run === "failed" && (
        <p className="form-error" role="alert">
          The checks could not be started. Please try again.
        </p>
      )}

      <section className="panel" aria-labelledby="teams-title">
        <div className="panel__head">
          <h2 className="panel__title" id="teams-title">
            Teams
          </h2>
          {projects.length > 0 && (
            <form action={runEventAction.bind(null, event.id)}>
              <SubmitButton pendingText="Starting…">Check all new projects</SubmitButton>
            </form>
          )}
        </div>
        {projects.length === 0 ? (
          <div className="panel__empty">
            <p>No teams yet. Add the first team below.</p>
          </div>
        ) : (
          <div className="table__wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Team</th>
                  <th scope="col">Status</th>
                  <th scope="col">TalNex score</th>
                  <th scope="col">Coverage</th>
                  {event.mode === "fixed_problem" && <th scope="col">Weighted total</th>}
                  <th scope="col">Flags</th>
                  <th scope="col">Links</th>
                  <th scope="col">
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => {
                  const status = projectStatus(p.status);
                  const href = `${path}/projects/${encodeURIComponent(p.id)}`;
                  return (
                    <tr key={p.id}>
                      <td>
                        <Link href={href} className="table__link">
                          {p.team_name}
                        </Link>
                      </td>
                      <td>
                        <span className={BADGE_CLASS[status.tone]}>{status.text}</span>
                      </td>
                      <td>{p.talnex_score10 === null ? "–" : `${formatScore(p.talnex_score10)}/10`}</td>
                      <td>{p.coverage === null ? "–" : formatCoverage(p.coverage)}</td>
                      {event.mode === "fixed_problem" && (
                        <td>{p.weighted_total === null ? "–" : `${formatScore(p.weighted_total / 10)}/10`}</td>
                      )}
                      <td>{flagCountText(p.flags)}</td>
                      <td>{linksGiven(p)}</td>
                      <td className="table__end">
                        <Link href={href} className="table__open" aria-label={`Open ${p.team_name}`}>
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
        <p className="panel__foot note">
          Teams are listed by name, not by score. TalNex does not rank teams or pick a winner.
        </p>
      </section>

      <section className="panel" aria-labelledby="add-title">
        <div className="panel__head">
          <h2 className="panel__title" id="add-title">
            Add a team
          </h2>
        </div>
        <div className="panel__body">
          <ProjectForm eventId={event.id} />
        </div>
      </section>

      <section className="panel" aria-labelledby="details-title">
        <div className="panel__head">
          <h2 className="panel__title" id="details-title">
            Event details
          </h2>
        </div>
        <dl className="definition panel__body">
          <dt>Starts</dt>
          <dd>{formatDate(event.starts_at)}</dd>
          <dt>Ends</dt>
          <dd>{formatDate(event.ends_at)}</dd>
          <dt>Sponsor tools</dt>
          <dd>{event.sponsor_tools.length ? event.sponsor_tools.join(", ") : "None listed"}</dd>
          {criteria.length > 0 && (
            <>
              <dt>Criteria</dt>
              <dd>
                <ul className="plain-list stack stack--tight">
                  {criteria.map((c) => (
                    <li key={c.id ?? c.name}>
                      <strong>{c.name}</strong> · weight {c.weight}
                      {c.description && ` · ${c.description}`}
                    </li>
                  ))}
                </ul>
              </dd>
            </>
          )}
        </dl>
      </section>
    </div>
  );
}
