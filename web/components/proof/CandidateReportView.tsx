import { FlagList } from "@/components/flags/FlagBadge";
import { EvidenceFacts } from "@/components/proof/EvidenceFacts";
import { GithubCard, GithubSummary } from "@/components/proof/GithubCard";
import { InterviewKit } from "@/components/proof/InterviewKit";
import { ProjectCard } from "@/components/proof/ProjectCard";
import { RerunButton } from "@/components/proof/RerunButton";
import { StatTile } from "@/components/ui/StatTile";
import { Tabs } from "@/components/ui/Tabs";
import { BADGE_CLASS, formatCost, formatDate, formatDuration } from "@/lib/format";
import { insightTone } from "@/lib/insights";
import { pasteCard, replaySummary } from "@/lib/leetcode-format";
import { SITE_NAMES, evidenceFacts, reportSummary, signalWeightInfo } from "@/lib/report-format";
import { githubCard } from "@/lib/report-layout";
import { weightedScore } from "@/lib/role-score";
import type { CandidateReport, CodingSignal } from "@/lib/types";

export const CANDIDATE_TABS = ["overview", "projects", "github", "coding", "interview", "jobs", "live"] as const;

const githubProfile = (report: CandidateReport) =>
  report.coding_signals.find((s) => s.site === "github" && s.signal === "github_profile");

function Overview({ report, criteria, details }: { report: CandidateReport; criteria: { name: string; weight: number }[]; details: React.ReactNode }) {
  const weighted = criteria.length > 0 ? weightedScore(report, criteria) : null;
  const summary = reportSummary(report);
  const saved = report.time_saved;
  const github = githubCard(githubProfile(report));
  return (
    <div className="stack">
      {details}
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
          Results so far: {summary.projectsTested} of {summary.projectsTotal} projects checked. The rest appear as they
          finish, then the final report.
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
            <p className="note">Must-have skills shown by features that worked in testing. “Not seen” only means no tested feature showed it.</p>
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

      {github && (
        <section className="panel" aria-labelledby="github-overview-title">
          <div className="panel__head">
            <h2 className="panel__title" id="github-overview-title">
              GitHub
            </h2>
          </div>
          <div className="panel__body">
            <GithubSummary data={github} />
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
        TalNex shows evidence, not a verdict on the person. There is no overall score or ranking; a human decides. Report
        made {formatDate(report.generated_at)}.
      </p>
    </div>
  );
}

function SignalCard({ signal }: { signal: CodingSignal }) {
  const weight = signalWeightInfo(signal.weight);
  const summary = replaySummary(signal);
  if (summary) return <p className="note">{summary}</p>;
  const paste = pasteCard(signal);
  if (paste)
    return (
      <div className="signal paste-card">
        <div className="row">
          <strong>{paste.title}</strong>
          <span className={BADGE_CLASS[weight.tone]}>{weight.text}</span>
        </div>
        <ul className="report-list">
          {paste.lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {paste.reason && <p className="note">{paste.reason}</p>}
        {paste.snippet && (
          <details className="proof-viewer">
            <summary>What was pasted</summary>
            <pre className="paste-card__code">{paste.snippet}</pre>
          </details>
        )}
        {paste.link && (
          <a className="meta" href={paste.link} target="_blank" rel="noopener noreferrer">
            {paste.linkText}
          </a>
        )}
      </div>
    );
  return (
    <div className="signal">
      <div className="row">
        <strong>{SITE_NAMES[signal.site] ?? signal.site}</strong>
        <span className={BADGE_CLASS[weight.tone]}>{weight.text}</span>
        <span className="meta">{signal.signal.replace(/_/g, " ")}</span>
        {signal.contest && <span className="meta">{signal.contest}</span>}
      </div>
      <EvidenceFacts facts={evidenceFacts(signal.evidence)} />
    </div>
  );
}

function CodingProfiles({ report }: { report: CandidateReport }) {
  const signals = report.coding_signals.filter((s) => s.site !== "github");
  return (
    <section className="panel" aria-labelledby="signals-title">
      <div className="panel__head">
        <h2 className="panel__title" id="signals-title">
          Coding profile signals
        </h2>
        <RerunButton candidateId={report.candidate_id}>Re-run coding checks</RerunButton>
      </div>
      <div className="panel__body stack">
        <p className="note">Hints to look at, not proof of anything. TalNex does not check that a profile is theirs.</p>
        {(report.profile_insights ?? []).length > 0 && (
          <ul className="insights">
            {(report.profile_insights ?? []).map((insight) => {
              const tone = insightTone(insight.evidence?.tone);
              return (
                <li className="insights__item" key={`${insight.site}-${insight.signal}`}>
                  <span className={BADGE_CLASS[tone.badge]}>{tone.text}</span>
                  <span>{String(insight.evidence?.summary ?? "")}</span>
                </li>
              );
            })}
          </ul>
        )}
        {signals.length === 0 &&<p className="note">No coding profile signals for this candidate.</p>}
        {signals.map((signal, i) => (
          <SignalCard key={`${signal.site}-${signal.signal}-${i}`} signal={signal} />
        ))}
      </div>
    </section>
  );
}

function GithubTab({ report }: { report: CandidateReport }) {
  const profile = githubProfile(report);
  const card = githubCard(profile);
  const others = report.coding_signals.filter((s) => s.site === "github" && s !== profile);
  if (!card && others.length === 0)
    return <p className="note">No GitHub account was found for this candidate. That never counts against anyone.</p>;
  return (
    <div className="stack">
      {card && <GithubCard data={card} />}
      {others.map((signal, i) => (
        <SignalCard key={`gh-${i}`} signal={signal} />
      ))}
    </div>
  );
}

/**
 * The recruiter proof report as tabs: Overview, Projects, GitHub, Coding profiles, Interview kit, Jobs and Live. The
 * open tab lives in ?tab= so a refresh or a shared link keeps it. There is no overall score and no ranking.
 */
export function CandidateReportView({
  report,
  criteria = [],
  initialTab,
  details,
  jobs,
  live,
}: {
  report: CandidateReport | null;
  criteria?: { name: string; weight: number }[];
  initialTab?: string;
  details: React.ReactNode;
  jobs: React.ReactNode;
  live: React.ReactNode;
}) {
  const waiting = <p className="note">The report appears here once the first project has been checked.</p>;
  return (
    <Tabs
      label="Candidate report"
      param="tab"
      initial={initialTab}
      tabs={[
        { id: "overview", label: "Overview", content: report ? <Overview report={report} criteria={criteria} details={details} /> : <div className="stack">{details}{waiting}</div> },
        {
          id: "projects",
          label: `Projects${report ? ` (${report.projects.length})` : ""}`,
          content: report ? (
            <div className="stack">
              {report.projects.map((project) => (
                <ProjectCard key={project.id} project={project} candidateId={report.candidate_id} />
              ))}
            </div>
          ) : (
            waiting
          ),
        },
        { id: "github", label: "GitHub", content: report ? <GithubTab report={report} /> : waiting },
        { id: "coding", label: "Coding profiles", content: report ? <CodingProfiles report={report} /> : waiting },
        {
          id: "interview",
          label: "Interview kit",
          content:
            report && (report.interview_kit ?? []).length > 0 ? (
              <InterviewKit questions={report.interview_kit ?? []} />
            ) : (
              <p className="note">No interview questions yet: they come from what TalNex found.</p>
            ),
        },
        { id: "jobs", label: "Jobs", content: jobs },
        { id: "live", label: "Live", content: live },
      ]}
    />
  );
}
