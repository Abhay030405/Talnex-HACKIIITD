import { FlagList } from "@/components/flags/FlagBadge";
import { ClaimRow } from "@/components/proof/ClaimRow";
import { EvidenceFacts } from "@/components/proof/EvidenceFacts";
import { NetworkBlock } from "@/components/proof/NetworkBlock";
import { RerunButton } from "@/components/proof/RerunButton";
import { VmTestPanel } from "@/components/proof/VmTestPanel";
import { WalkthroughBox } from "@/components/proof/WalkthroughBox";
import { ProjectScore } from "@/components/scores/ProjectScore";
import { Tabs } from "@/components/ui/Tabs";
import { BADGE_CLASS, formatDate } from "@/lib/format";
import { networkSummary } from "@/lib/network";
import { evidenceFacts, projectStatusInfo } from "@/lib/report-format";
import { VERDICT_GROUP_TITLE, VERDICT_ORDER, groupByVerdict, projectAuthorship, verdictCounts } from "@/lib/report-layout";
import type { ReportFeature, ReportProject } from "@/lib/types";

const BAR_WORDS: Record<(typeof VERDICT_ORDER)[number], string> = {
  works: "work",
  partly_works: "partly work",
  broken: "broken",
  reviewed_from_code: "reviewed from code",
  could_not_test: "could not test",
};

/** A stacked bar of the verdicts, with the counts in words beside it. */
export function VerdictBar({ features }: { features: ReportFeature[] }) {
  const counts = verdictCounts(features);
  const order = ["works", "partly_works", "broken", "reviewed_from_code", "could_not_test"] as const;
  const shown = order.filter((v) => counts[v] > 0);
  if (shown.length === 0) return null;
  return (
    <div className="verdict-bar">
      <div className="verdict-bar__track" aria-hidden="true">
        {shown.map((v) =>
          Array.from({ length: counts[v] }, (_, i) => <span key={`${v}-${i}`} className={`verdict-bar__part verdict-bar__part--${v}`} />),
        )}
      </div>
      <p className="meta">{shown.map((v) => `${counts[v]} ${BAR_WORDS[v]}`).join(" · ")}</p>
    </div>
  );
}

/** Claims grouped by verdict, worst first; "could not test" folded away. Shared with the hackathon card. */
export function FeaturesTab({ features, flags }: { features: ReportFeature[]; flags: ReportProject["flags"] }) {
  const groups = groupByVerdict(features);
  if (groups.length === 0) return <p className="note">No claims were found for this project.</p>;
  return (
    <div className="stack">
      <FlagList flags={flags} />
      {groups.map((g) =>
        g.verdict === "could_not_test" ? (
          <details className="proof-viewer claims-untested" key={g.verdict} open={groups.length === 1}>
            <summary>
              {g.features.length} {g.features.length === 1 ? "claim" : "claims"} could not be tested (not counted against
              anyone)
            </summary>
            <div className="claims">
              {g.features.map((f) => (
                <ClaimRow key={f.claim_id} feature={f} />
              ))}
            </div>
          </details>
        ) : (
          <section className="stack stack--tight" key={g.verdict} aria-label={VERDICT_GROUP_TITLE[g.verdict]}>
            <h3 className="claims__group-title">
              {VERDICT_GROUP_TITLE[g.verdict]} ({g.features.length})
            </h3>
            <div className="claims">
              {g.features.map((f) => (
                <ClaimRow key={f.claim_id} feature={f} />
              ))}
            </div>
          </section>
        ),
      )}
    </div>
  );
}

/** Network and console totals, then each step's calls. Shared with the hackathon card. */
export function NetworkTab({ features }: { features: ReportFeature[] }) {
  const network = networkSummary(features);
  if (!network) return <p className="note">No network or console activity was recorded for this project.</p>;
  const steps = features.flatMap((f) => f.proof.filter((s) => s.devtools).map((s) => ({ feature: f.text, step: s })));
  return (
    <div className="stack">
      <dl className="definition">
        <dt>API calls</dt>
        <dd>{network.apiCalls}</dd>
        {network.averageMs !== null && (
          <>
            <dt>Latency</dt>
            <dd>
              average {network.averageMs} ms · slowest {network.slowestMs} ms
            </dd>
          </>
        )}
        <dt>Failed or error answers</dt>
        <dd>{network.errors}</dd>
        <dt>Console errors</dt>
        <dd>{network.consoleErrors}</dd>
        <dt>Leaked secrets</dt>
        <dd className={network.leaks > 0 ? "network__bad" : undefined}>{network.leaks > 0 ? `${network.leaks} (masked below)` : "none seen"}</dd>
      </dl>
      {steps.map(({ feature, step }, i) => (
        <details className="proof-viewer" key={i}>
          <summary>
            {feature} · step {step.step}: {step.action}
          </summary>
          <NetworkBlock devtools={step.devtools} />
        </details>
      ))}
    </div>
  );
}

function RepositoryTab({ project }: { project: ReportProject }) {
  const o = project.originality;
  const languages = Object.entries(o?.languages ?? {}).sort((a, b) => b[1] - a[1]);
  const authors = projectAuthorship(project.features);
  const candidateShare = project.features.find((f) => f.authorship?.candidate_share != null)?.authorship?.candidate_share;
  return (
    <div className="stack">
      {project.repo_url ? (
        <a className="table__link" href={project.repo_url} target="_blank" rel="noopener noreferrer">
          {project.repo_url.replace(/^https?:\/\//, "")}
        </a>
      ) : (
        <p className="note">No repository link was given for this project.</p>
      )}
      {o && (
        <dl className="definition">
          <dt>Created</dt>
          <dd>{o.created_at ? formatDate(o.created_at) : "unknown"}</dd>
          <dt>Last pushed</dt>
          <dd>{o.pushed_at ? formatDate(o.pushed_at) : "unknown"}</dd>
          <dt>Original or fork</dt>
          <dd>{o.repo_found ? (o.fork ? "a fork of another repository" : "original (not a fork)") : "not checked"}</dd>
          {languages.length > 0 && (
            <>
              <dt>Languages</dt>
              <dd>
                <span className="row">
                  {languages.map(([name]) => (
                    <span className="chip" key={name}>
                      {name}
                    </span>
                  ))}
                </span>
              </dd>
            </>
          )}
        </dl>
      )}
      {o && o.notes.length > 0 && (
        <ul className="report-list">
          {o.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
      <div className="stack stack--tight">
        <h3 className="claims__group-title">Who wrote it</h3>
        {authors.length === 0 ? (
          <p className="note">The code behind the claims was not traced to its authors.</p>
        ) : (
          <>
            {candidateShare != null && (
              <p className="note">
                The candidate&apos;s own account wrote about <strong>{Math.round(candidateShare * 100)}%</strong> of the traced code.
              </p>
            )}
            <div className="table__wrap">
              <table className="table table--compact">
                <thead>
                  <tr>
                    <th scope="col">Account</th>
                    <th scope="col">Share of traced lines</th>
                    <th scope="col">Commits</th>
                    <th scope="col">Pushed</th>
                  </tr>
                </thead>
                <tbody>
                  {authors.map((a) => (
                    <tr key={a.account} className="table__row--static">
                      <td>{a.account === "unlinked" ? "No linked account" : a.account}</td>
                      <td>{Math.round(a.share * 100)}%</td>
                      <td>{a.commits}</td>
                      <td>
                        {a.first_pushed_at ? formatDate(a.first_pushed_at) : "?"}
                        {a.last_pushed_at && a.last_pushed_at !== a.first_pushed_at ? ` – ${formatDate(a.last_pushed_at)}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">Shares are rough: two features can trace the same lines.</p>
          </>
        )}
      </div>
      {project.engineering && (
        <div className="stack stack--tight">
          <h3 className="claims__group-title">Engineering quality</h3>
          <EvidenceFacts facts={evidenceFacts(project.engineering)} />
        </div>
      )}
    </div>
  );
}

/** One resume project: a summary header, then Features, VM test, Network, Repository and Ask tabs. */
export function ProjectCard({ project, candidateId }: { project: ReportProject; candidateId?: string }) {
  const status = projectStatusInfo(project.status);
  return (
    <section className="panel" aria-labelledby={`project-${project.id}`}>
      <div className="panel__head project-card__head">
        <div className="stack stack--tight">
          <h2 className="panel__title" id={`project-${project.id}`}>
            {project.name}
          </h2>
          <div className="row">
            <span className={BADGE_CLASS[status.tone]}>{status.text}</span>
            {candidateId && (
              <RerunButton candidateId={candidateId} projectId={project.id}>
                Re-test this project
              </RerunButton>
            )}
            {project.live_url && (
              <a className="meta" href={project.live_url} target="_blank" rel="noopener noreferrer">
                Live site
              </a>
            )}
            {project.repo_url && (
              <a className="meta" href={project.repo_url} target="_blank" rel="noopener noreferrer">
                Repository
              </a>
            )}
          </div>
          <VerdictBar features={project.features} />
          {project.status !== "tested" && (
            <p className="note">
              {project.status_reason || "This project could not be tested."} This does not count against the candidate.
            </p>
          )}
        </div>
        {project.talnex && <ProjectScore talnex={project.talnex} />}
      </div>
      <div className="panel__body">
        <Tabs
          label={`${project.name} sections`}
          tabs={[
            { id: "features", label: "Features", content: <FeaturesTab features={project.features} flags={project.flags} /> },
            { id: "vm", label: "VM test", content: <VmTestPanel sandbox={project.sandbox} /> },
            { id: "network", label: "Network", content: <NetworkTab features={project.features} /> },
            { id: "repository", label: "Repository", content: <RepositoryTab project={project} /> },
            {
              id: "ask",
              label: "Ask",
              content:
                project.features.length > 0 ? (
                  <WalkthroughBox subject="candidate_project" subjectId={project.id} />
                ) : (
                  <p className="note">There is nothing to ask about yet.</p>
                ),
            },
          ]}
        />
      </div>
    </section>
  );
}
