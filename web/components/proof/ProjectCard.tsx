import Link from "next/link";

import { RerunButton } from "@/components/proof/RerunButton";
import { FlagList } from "@/components/flags/FlagBadge";
import { ClaimRow } from "@/components/proof/ClaimRow";
import { WalkthroughBox } from "@/components/proof/WalkthroughBox";
import { ProjectScore } from "@/components/scores/ProjectScore";
import { BADGE_CLASS, formatDate } from "@/lib/format";
import { networkSummary } from "@/lib/network";
import { projectStatusInfo } from "@/lib/report-format";
import type { ReportProject } from "@/lib/types";

/** One resume project: status, score with coverage, flags beside it, each claim with its proof, and code history. */
export function ProjectCard({
  project,
  tourHref,
  candidateId,
}: {
  project: ReportProject;
  tourHref?: string;
  candidateId?: string;
}) {
  const status = projectStatusInfo(project.status);
  const network = networkSummary(project.features);
  const originality = project.originality;
  const languages = Object.keys(originality?.languages ?? {});

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
          {network && (
            <p className="meta">
              Network: {network.apiCalls} API calls
              {network.averageMs !== null && `, average ${network.averageMs} ms, slowest ${network.slowestMs} ms`}
              {`, ${network.errors} failed or error answers, ${network.consoleErrors} console errors`}
              {network.leaks > 0 && <span className="network__bad">{`, ${network.leaks} leaked secrets (masked below)`}</span>}
            </p>
          )}
          {project.status !== "tested" && (
            <p className="note">
              {project.status_reason || "This project could not be tested."} This does not count against the candidate.
            </p>
          )}
        </div>
        {project.talnex && <ProjectScore talnex={project.talnex} />}
      </div>

      <div className="panel__body stack">
        <FlagList flags={project.flags} />

        {project.features.length > 0 && (
          <div className="claims">
            {project.features.map((feature) => (
              <ClaimRow key={feature.claim_id} feature={feature} />
            ))}
          </div>
        )}

        {originality && (
          <dl className="definition">
            <dt>Code history</dt>
            <dd>
              {originality.repo_found
                ? [
                    `Started ${originality.created_at ? formatDate(originality.created_at) : "on an unknown date"}`,
                    `last change ${originality.pushed_at ? formatDate(originality.pushed_at) : "unknown"}`,
                    originality.fork ? "copied (forked) from another repository" : "not a fork",
                    ...(languages.length ? [languages.join(", ")] : []),
                  ].join(" · ")
                : "The repository was not checked."}
            </dd>
            {originality.notes.length > 0 && (
              <>
                <dt>Notes</dt>
                <dd>
                  <ul className="plain-list stack stack--tight">
                    {originality.notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>
        )}

        {project.features.length > 0 && tourHref && (
          <div className="walkthrough__tour">
            <Link className="button button--primary button--sm" href={tourHref}>
              Walk me through it
            </Link>
            <span className="note">A chat beside the live site: the guide reads the code and shows how a feature was built.</span>
          </div>
          )}
        {project.features.length > 0 && <WalkthroughBox subject="candidate_project" subjectId={project.id} />}
      </div>
    </section>
  );
}
