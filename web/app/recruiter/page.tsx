import type { Metadata } from "next";
import Link from "next/link";

import { ArrowIcon, PlusIcon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { BADGE_CLASS, candidateStatus, countByStage, formatDate } from "@/lib/format";
import { load } from "@/lib/load";
import { requireRole } from "@/lib/session";
import { roleLabel, type CandidateSummary, type JobRole } from "@/lib/types";

export const metadata: Metadata = { title: "Candidates" };

export default async function RecruiterWorkspace() {
  const session = await requireRole("recruiter");
  const { data, problem } = await load<CandidateSummary[]>("/v1/candidates", "your candidates");
  const roles = (await load<JobRole[]>("/v1/roles", "your roles")).data ?? [];
  const candidates = data ?? [];
  const counts = countByStage(candidates);
  const name = session.user.name || session.user.email || "there";

  return (
    <div className="stack">
      <PageHeader
        title="Candidates"
        lead={`Welcome back, ${name}. Every check shows its proof.`}
        actions={
          <div className="row">
            <Link href="/new/role" className="button button--primary">
              <PlusIcon size={16} />
              New role (one or many resumes)
            </Link>
            <Link href="/new/recruiter" className="button button--ghost">
              Quick check (one resume)
            </Link>
          </div>
        }
      />

      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : (
        <>
          <div className="stats">
            <StatTile
              label="Needs your check"
              value={counts.needs_you}
              hint="Confirm what the resume reader found"
              highlight={counts.needs_you > 0}
            />
            <StatTile label="In progress" value={counts.working} hint="Being read or tested" />
            <StatTile label="Finished" value={counts.finished} hint="Proof report ready" />
            <StatTile label="Failed" value={counts.failed} hint="Could not finish" />
          </div>

          {roles.length > 0 && (
            <section className="panel" aria-labelledby="all-roles">
              <div className="panel__head">
                <h2 className="panel__title" id="all-roles">
                  Roles
                </h2>
                <span className="meta">{roles.length} total</span>
              </div>
              <ul className="report-list">
                {roles.map((role) => (
                  <li key={role.id}>
                    <Link href={`/roles/${role.id}`} className="table__link">
                      {role.title}
                    </Link>{" "}
                    <span className="meta">
                      {roleLabel(role.role_level)} · {role.candidate_count}{" "}
                      {role.candidate_count === 1 ? "resume" : "resumes"} · {formatDate(role.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="panel" aria-labelledby="all-candidates">
            <div className="panel__head">
              <h2 className="panel__title" id="all-candidates">
                All candidates
              </h2>
              <span className="meta">{candidates.length} total</span>
            </div>
            {candidates.length === 0 ? (
              <div className="panel__empty">
                <p>No checks yet. Add a candidate to get your first proof report.</p>
                <Link href="/new/recruiter" className="button button--soft">
                  <PlusIcon size={16} />
                  Start a check
                </Link>
              </div>
            ) : (
              <div className="table__wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Candidate</th>
                      <th scope="col">Judged as</th>
                      <th scope="col">Status</th>
                      <th scope="col">Added</th>
                      <th scope="col">
                        <span className="sr-only">Open</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((candidate) => {
                      const status = candidateStatus(candidate.status);
                      const href = `/candidates/${candidate.id}`;
                      return (
                        <tr key={candidate.id}>
                          <td>
                            <Link href={href} className="table__link">
                              {candidate.label || "Unnamed candidate"}
                            </Link>
                          </td>
                          <td>{roleLabel(candidate.role_level)}</td>
                          <td>
                            <span className={BADGE_CLASS[status.tone]}>{status.text}</span>
                          </td>
                          <td>{formatDate(candidate.created_at)}</td>
                          <td className="table__end">
                            <Link
                              href={href}
                              className="table__open"
                              aria-label={`Open ${candidate.label || "candidate"}`}
                            >
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
