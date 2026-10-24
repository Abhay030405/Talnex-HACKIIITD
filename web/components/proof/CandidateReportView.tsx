import { Fragment } from "react";

import { FlagList } from "@/components/flags/FlagBadge";
import { ProjectCard } from "@/components/proof/ProjectCard";
import { StatTile } from "@/components/ui/StatTile";
import { BADGE_CLASS, formatDate } from "@/lib/format";
import { SITE_NAMES, evidenceFacts, reportSummary, signalWeightInfo } from "@/lib/report-format";
import type { CandidateReport } from "@/lib/types";

/** The whole recruiter proof report. There is no overall candidate score and no ranking: a human decides. */
export function CandidateReportView({ report }: { report: CandidateReport }) {
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
      </div>

      {report.has_gaps && (
        <p className="notice" role="status">
          Some parts could not be tested. They are shown with the reason and do not count against the candidate.
        </p>
      )}

      {report.projects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}

      {report.coding_signals.length > 0 && (
        <section className="panel" aria-labelledby="signals-title">
          <div className="panel__head">
            <h2 className="panel__title" id="signals-title">
              Coding profile signals
            </h2>
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
