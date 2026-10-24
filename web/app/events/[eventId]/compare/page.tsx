import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/ui/PageHeader";
import { BADGE_CLASS } from "@/lib/format";
import { getEventCompare } from "@/lib/project-card";
import { flagLevelInfo, formatScore, verdictInfo } from "@/lib/report-format";
import { requireRole } from "@/lib/session";
import type { BestTeam } from "@/lib/types";

export const metadata: Metadata = { title: "Who built each feature best" };

function BestTeams({ eventId, teams }: { eventId: string; teams: BestTeam[] }) {
  return (
    <ul className="plain-list best-teams">
      {teams.map((team) => {
        const verdict = verdictInfo(team.verdict);
        return (
          <li key={team.claim_id} className="best-team">
            <Link
              className="best-team__name"
              href={`/events/${encodeURIComponent(eventId)}/projects/${encodeURIComponent(team.project_id)}`}
            >
              {team.team_name}
            </Link>
            <div className="row">
              <span className={BADGE_CLASS[verdict.tone]}>{verdict.text}</span>
              {team.feature_score !== null && <span className="meta">{formatScore(team.feature_score)}/10</span>}
            </div>
            <span className="note">{team.claim_text}</span>
            {team.reason && <span className="note">{team.reason}</span>}
            {team.proof_urls.length > 0 && (
              <div className="row">
                {team.proof_urls.map((url, i) => (
                  <a key={url} className="meta" href={url} target="_blank" rel="noopener noreferrer">
                    Proof {i + 1}
                  </a>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Up to three teams per feature that built it best. Never one winner, no ranking between teams or features. */
export default async function ComparePage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  await requireRole("organizer");

  const compare = await getEventCompare(eventId);
  if (!compare) notFound();
  const back = { href: `/events/${encodeURIComponent(eventId)}`, label: "Back to the event" };

  return (
    <div className="stack">
      <PageHeader
        title="Who built each feature best"
        lead="For each feature, up to three teams that built it best. This is not a ranking and there is no winner: you decide."
        back={back}
      />

      {!compare.ready && (
        <p className="notice" role="status">
          The comparison is still being worked out. It fills in once the checks of the whole event have finished.
        </p>
      )}

      {compare.features.length > 0 && (
        <section className="stack" aria-labelledby="features-title">
          <h2 className="section__title" id="features-title">
            By feature
          </h2>
          <div className="grid grid--2">
            {compare.features.map((f) => (
              <section className="card" key={f.name} aria-label={f.name}>
                <h3 className="card__title">{f.name}</h3>
                <BestTeams eventId={eventId} teams={f.best_teams} />
              </section>
            ))}
          </div>
        </section>
      )}

      {compare.group_bests.length > 0 && (
        <section className="stack" aria-labelledby="groups-title">
          <h2 className="section__title" id="groups-title">
            By group
          </h2>
          <div className="grid grid--2">
            {compare.group_bests.map((g) => (
              <section className="card" key={g.name} aria-label={g.name}>
                <h3 className="card__title">{g.name}</h3>
                <BestTeams eventId={eventId} teams={g.best_teams} />
              </section>
            ))}
          </div>
        </section>
      )}

      {compare.copy_pairs.length > 0 && (
        <section className="panel" aria-labelledby="pairs-title">
          <div className="panel__head">
            <h2 className="panel__title" id="pairs-title">
              Teams with code of the same shape
            </h2>
          </div>
          <ul className="panel__body plain-list stack stack--tight">
            {compare.copy_pairs.map((pair) => {
              const level = flagLevelInfo(pair.level ?? "info");
              return (
                <li key={`${pair.team_a.id}-${pair.team_b.id}`} className="row">
                  <span className={BADGE_CLASS[level.tone]}>{level.text}</span>
                  <span>
                    {pair.team_a.name} and {pair.team_b.name}
                  </span>
                  <span className="meta">{Math.round(pair.shared_pct)}% shared</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {compare.ready && compare.features.length === 0 && compare.group_bests.length === 0 && (
        <p className="notice">No feature was built by two or more teams, so there is nothing to compare.</p>
      )}

      <ul className="report-list">
        {compare.notes.map((note, i) => (
          <li key={i}>{note}</li>
        ))}
      </ul>
    </div>
  );
}
