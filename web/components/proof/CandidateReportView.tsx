import { Fragment } from "react";

import { FlagList } from "@/components/flags/FlagBadge";
import { InterviewKit } from "@/components/proof/InterviewKit";
import { ProjectCard } from "@/components/proof/ProjectCard";
import { RerunButton } from "@/components/proof/RerunButton";
import { StatTile } from "@/components/ui/StatTile";
import { BADGE_CLASS, formatCost, formatDate, formatDuration } from "@/lib/format";
import { SITE_NAMES, evidenceFacts, reportSummary, signalWeightInfo } from "@/lib/report-format";
import { tourPageUrl } from "@/lib/tour";
import { weightedScore } from "@/lib/role-score";
import type { CandidateReport } from "@/lib/types";

/** The whole recruiter proof report. There is no overall candidate score and no ranking: a human decides. */
export function CandidateReportView({
  report,
  criteria = [],
  candidateId,
}: {
  report: CandidateReport;
  candidateId?: string;
  criteria?: { name: string; weight: number }[];
}) {
  const weighted = criteria.length > 0 ? weightedScore(report, criteria) : null;
  const summary = reportSummary(report);
  const saved = report.time_saved;

  return (
    <div className="stack">
      <div className="stats">
        <StatTile label="Projects tested" value={`${summary.projectsTested} of ${summary.projectsTotal}`} />
        <StatTile label="Features scored" value={`${summary.featuresScored} of ${summary.featuresTotal}`} />
        <StatTile
          label="Time saved (estimate)"
          value={`about ${saved.saved_minutes} min`}
          hint={`By hand: roughly ${saved.manual_minutes_estimate} min. TalNex: about ${saved.talnex_minutes} min.`}
        />
        {report.run && (
          <StatTile
            label="Time and cost of this check"
            value={`${formatDuration(report.run.seconds)} · ${formatCost(report.run.cost_usd)}`}
            hint={`Model ${formatCost(report.run.model_usd)} (${report.run.model_calls} calls) · browser ${formatCost(report.run.browser_usd)} (${report.run.browser_sessions} sessions).`}
          />
        )}
      </div>

      {report.partial && (
        <p className="notice" role="status">
          Results so far: {summary.projectsTested} of {summary.projectsTotal} projects checked. The rest appear here as
          they finish, then the final report.
        </p>
      )}

      {report.has_gaps && !report.partial && (
        <p className="notice" role="status">
          Some parts could not be tested. They are shown with the reason and do not count against the candidate.
        </p>
      )}

      {weighted && (
        <section className="panel" aria-labelledby="weighted-title">
          <div className="panel__head">
            <h2 className="panel__title" id="weighted-title">
              Weighted score for this role: {weighted.score === null ? "not scored yet" : `${weighted.score} / 10`}
            </h2>
          </div>
          <div className="panel__body stack">
            <p className="note">Uses the role&apos;s weights as they are now. Change them in the role settings; nothing is re-tested.</p>
            <ul className="report-list">
              {weighted.parts.map((p) => (
                <li key={p.name}>
                  <strong>{p.name}</strong> (weight {p.weight}):{" "}
                  {p.average === null ? "no scored features in this group, left out" : `${p.average.toFixed(1)} / 10 from ${p.features} features`}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {report.role && report.role.skills.length > 0 && (
        <section className="panel" aria-labelledby="fit-title">
          <div className="panel__head">
            <h2 className="panel__title" id="fit-title">
              Fit to the role: {report.role.title}
            </h2>
          </div>
          <div className="panel__body stack">
            <p className="note">
              Must-have skills shown by features that worked in testing. “Not seen” only means no tested feature showed it.
            </p>
            <ul className="report-list">
              {report.role.skills.map((s) => (
                <li key={s.skill}>
                  <span className={s.proven_by.length ? "badge badge--success" : "badge badge--neutral"}>
                    {s.proven_by.length ? "Shown" : "Not seen"}
                  </span>{" "}
                  <strong>{s.skill}</strong>
                  {s.proven_by.length > 0 && <span className="meta"> by {s.proven_by.join("; ")}</span>}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <InterviewKit questions={report.interview_kit ?? []} />

      {report.projects.map((project) => (
        <ProjectCard
          key={project.id}
          project={project}
          candidateId={report.candidate_id}
          tourHref={candidateId ? tourPageUrl("candidate_project", project.id, candidateId) : undefined}
        />
      ))}

      {report.coding_signals.length > 0 && (
        <section className="panel" aria-labelledby="signals-title">
          <div className="panel__head">
            <h2 className="panel__title" id="signals-title">
              Coding profile signals
            </h2>
            <RerunButton candidateId={report.candidate_id}>Re-run coding checks</RerunButton>
          </div>
          <div className="panel__body stack">
            <p className="note">
              Hints to look at, not proof of anything. TalNex does not check that a profile is theirs.
            </p>
            {report.coding_signals.map((signal, i) => {
              const weight = signalWeightInfo(signal.weight);
              const facts = evidenceFacts(signal.evidence);
              return (
                <div className="signal" key={`${signal.site}-${signal.signal}-${i}`}>
                  <div className="row">
                    <strong>{SITE_NAMES[signal.site] ?? signal.site}</strong>
                    <span className={BADGE_CLASS[weight.tone]}>{weight.text}</span>
                    <span className="meta">{signal.signal.replace(/_/g, " ")}</span>
                    {signal.contest && <span className="meta">{signal.contest}</span>}
                  </div>
                  {facts.length > 0 && (
                    <dl className="definition">
                      {facts.map((fact) => (
                        <Fragment key={fact.label}>
                          <dt>{fact.label}</dt>
                          <dd>{fact.value}</dd>
                        </Fragment>
                      ))}
                    </dl>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {(report.flags.length > 0 || report.notes.length > 0) && (
        <section className="panel" aria-labelledby="notes-title">
          <div className="panel__head">
            <h2 className="panel__title" id="notes-title">
              Flags and notes
            </h2>
          </div>
          <div className="panel__body stack">
            <FlagList flags={report.flags} />
            {report.notes.length > 0 && (
              <ul className="report-list">
                {report.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      <p className="note">
        TalNex shows evidence, not a verdict on the person. There is no overall score or ranking; a human decides.
        Report made {formatDate(report.generated_at)}.
      </p>
    </div>
  );
}
