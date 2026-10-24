import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { ArrowIcon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { ApiError, apiFetch } from "@/lib/api";
import { BADGE_CLASS, candidateStatus, countByStage, formatDate } from "@/lib/format";
import { isFinishedStatus } from "@/lib/progress-format";
import { requireRole } from "@/lib/session";
import { ROLE_CHECKS, roleLabel, type JobRole } from "@/lib/types";

export const metadata: Metadata = { title: "Role" };

/** One job opening: what it asks for, and every candidate uploaded to it as their checks come in. No ranking. */
export default async function RolePage({ params }: { params: Promise<{ roleId: string }> }) {
  await requireRole("recruiter");
  const { roleId } = await params;
  let role: JobRole;
  try {
    role = await apiFetch<JobRole>(`/v1/roles/${encodeURIComponent(roleId)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) notFound();
    throw error;
  }
  const candidates = role.candidates ?? [];
  const counts = countByStage(candidates);
  const running = candidates.some((c) => !isFinishedStatus(c.status) && c.status !== "awaiting_confirmation");
  const checks = ROLE_CHECKS.filter((c) => Object.keys(role.checks).length === 0 || role.checks[c.value]);

  return (
    <div className="stack">
      <PageHeader
        title={role.title}
        lead={`${roleLabel(role.role_level)} role · ${candidates.length} ${candidates.length === 1 ? "resume" : "resumes"}`}
        back={{ href: "/recruiter", label: "All candidates" }}
        actions={
          <div className="row">
            <Link href={`/roles/${role.id}/live`} className="button button--primary">
              Watch all live
            </Link>
            <Link href={`/roles/${role.id}/settings`} className="button button--ghost">
              Settings and weights
            </Link>
          </div>
        }
      />
      <AutoRefresh active={running} />

      <div className="stats">
        <StatTile label="Needs your check" value={counts.needs_you} highlight={counts.needs_you > 0} />
        <StatTile label="In progress" value={counts.working} hint="Being read or tested" />
        <StatTile label="Finished" value={counts.finished} hint="Proof report ready" />
        <StatTile label="Failed" value={counts.failed} hint="Could not finish" />
      </div>

      <section className="panel" aria-labelledby="role-candidates">
        <div className="panel__head">
          <h2 className="panel__title" id="role-candidates">
            Candidates
          </h2>
          <span className="meta">{running ? "Updating as results come in" : "Up to date"}</span>
        </div>
        <div className="table__wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Candidate</th>
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
                    <td>
                      <span className={BADGE_CLASS[status.tone]}>{status.text}</span>
                    </td>
                    <td>{formatDate(candidate.created_at)}</td>
                    <td className="table__end">
                      <Link href={href} className="table__open" aria-label={`Open ${candidate.label || "candidate"}`}>
                        <ArrowIcon size={16} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="role-brief">
        <div className="panel__head">
          <h2 className="panel__title" id="role-brief">
            What this role asks for
          </h2>
        </div>
        <div className="panel__body stack">
          {role.skills.length > 0 && (
            <div className="row">
              {role.skills.map((skill) => (
                <span className="badge badge--neutral" key={skill}>
                  {skill}
                </span>
              ))}
            </div>
          )}
          {role.person_wanted && <p className="note">The person: {role.person_wanted}</p>}
          {(role.criteria ?? []).length > 0 && (
            <ul className="report-list">
              {(role.criteria ?? []).map((c) => (
                <li key={c.name}>
                  {c.name} (weight {c.weight}){c.description ? `: ${c.description}` : ""}
                </li>
              ))}
            </ul>
          )}
          <p className="note">Checks: {checks.map((c) => c.label).join(", ")}.</p>
          {role.job_description && (
            <details className="proof-viewer">
              <summary>Job description</summary>
              <p className="note">{role.job_description}</p>
            </details>
          )}
        </div>
      </section>
    </div>
  );
}
