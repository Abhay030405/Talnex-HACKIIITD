import { AskTalnex, type Ask, type CustomTest } from "@/components/proof/AskTalnex";
import type { JobRole } from "@/lib/types";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect, unstable_rethrow } from "next/navigation";

import { CandidateReportView } from "@/components/proof/CandidateReportView";
import { ProgressPanel } from "@/components/proof/ProgressPanel";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { BADGE_CLASS, candidateStatus } from "@/lib/format";
import { getCandidateProgress } from "@/lib/progress";
import { canUploadResume, isFinishedStatus } from "@/lib/progress-format";
import { getCandidateReport } from "@/lib/report";
import { SITE_NAMES, statusWords } from "@/lib/report-format";
import { requireRole } from "@/lib/session";
import { roleLabel, type CandidateProgress, type CandidateSummary } from "@/lib/types";

import { uploadResumeAction } from "./actions";

export const metadata: Metadata = { title: "Recruiter check" };

const RESUME_MESSAGES: Record<string, string> = {
  failed: "The resume did not go through. Please upload it again.",
  invalid: "That file was not a PDF of 5 MB or less. Please choose the resume as a PDF.",
  busy: "A resume is still being read for this candidate. Wait for it to finish, then try again.",
};

export default async function CandidatePage({
  params,
  searchParams,
}: {
  params: Promise<{ candidateId: string }>;
  searchParams: Promise<{ resume?: string }>;
}) {
  const { candidateId } = await params;
  const { resume } = await searchParams;
  await requireRole("recruiter");
  const path = `/candidates/${encodeURIComponent(candidateId)}`;

  let candidate: CandidateSummary;
  try {
    candidate = await apiFetch<CandidateSummary>(`/v1/candidates/${encodeURIComponent(candidateId)}`);
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) notFound();
    throw error;
  }

  // Nothing is tested until the recruiter confirms what the resume reader found.
  if (candidate.status === "awaiting_confirmation") redirect(`${path}/confirm`);

  const report = await getCandidateReport(candidateId);
  let asks: Ask[] = [];
  if (report) {
    try {
      asks = await apiFetch<Ask[]>(`/v1/candidates/${encodeURIComponent(candidateId)}/asks`);
    } catch (error) {
      unstable_rethrow(error);
    }
  }
  let customTests: CustomTest[] = [];
  if (report) {
    const lists = await Promise.all(
      report.projects.map(async (p) => {
        try {
          const list = await apiFetch<CustomTest[]>(`/v1/candidate-projects/${encodeURIComponent(p.id)}/custom-tests`);
          return list.map((t) => ({ ...t, project: p.name }));
        } catch (error) {
          unstable_rethrow(error);
          return [];
        }
      }),
    );
    customTests = lists.flat();
  }
  let criteria: { name: string; weight: number }[] = [];
  if (candidate.role_id) {
    try {
      criteria = (await apiFetch<JobRole>(`/v1/roles/${encodeURIComponent(candidate.role_id)}`)).criteria ?? [];
    } catch (error) {
      unstable_rethrow(error);
    }
  }
  // A check running again keeps its old report on screen, so progress shows whenever something is still running.
  let progress: CandidateProgress | null = null;
  if (!report || !isFinishedStatus(candidate.status)) {
    try {
      progress = await getCandidateProgress(candidateId);
    } catch (error) {
      unstable_rethrow(error);
    }
  }
  const status = progress?.status ?? candidate.status;
  const badge = candidateStatus(status);
  const handles = Object.entries(candidate.coding_handles ?? {});

  return (
    <div className="stack">
      <PageHeader
        title={candidate.label || "Unnamed candidate"}
        back={{ href: "/recruiter", label: "All candidates" }}
        actions={
          <Link href={`${path}/live`} className="button button--ghost">
            Watch live
          </Link>
        }
      >
        <div className="row">
          <span className={BADGE_CLASS[badge.tone]}>{badge.text}</span>
          <span className="badge badge--neutral">Judged as {roleLabel(candidate.role_level)}</span>
        </div>
      </PageHeader>

      <AutoRefresh active={!isFinishedStatus(status) || [...asks, ...customTests].some((a) => a.status !== "done" && a.status !== "failed")} />

      {resume && RESUME_MESSAGES[resume] && (
        <p className="notice" role="alert">
          {RESUME_MESSAGES[resume]}
        </p>
      )}

      <section className="panel" aria-labelledby="details-title">
        <div className="panel__head">
          <h2 className="panel__title" id="details-title">
            Candidate details
          </h2>
        </div>
        <dl className="definition panel__body">
          <dt>Coding profiles</dt>
          <dd>
            {handles.length > 0
              ? handles.map(([site, handle]) => `${SITE_NAMES[site] ?? site}: ${handle}`).join(" · ")
              : "None added"}
          </dd>
        </dl>
      </section>

      {progress && (!report || !isFinishedStatus(status)) && <ProgressPanel progress={progress} />}

      {report ? (
        <>
          <AskTalnex
            candidateId={candidateId}
            asks={asks}
            customTests={customTests}
            projects={report.projects.map((p) => ({ id: p.id, name: p.name }))}
            roleId={candidate.role_id}
          />
          <CandidateReportView report={report} criteria={criteria} />
        </>
      ) : (
        <section className="panel" aria-labelledby="report-title">
          <div className="panel__head">
            <h2 className="panel__title" id="report-title">
              Proof report
            </h2>
          </div>
          <div className="panel__body">
            <p className="note">
              {statusWords(status)} The report appears here once every project has been checked. This page updates by
              itself.
            </p>
          </div>
        </section>
      )}

      {canUploadResume(status) && (
        <section className="panel" aria-labelledby="again-title">
          <div className="panel__head">
            <h2 className="panel__title" id="again-title">
              Check again with a resume
            </h2>
          </div>
          <form action={uploadResumeAction.bind(null, candidateId)} className="panel__body stack stack--tight">
            <p className="note">The resume file is deleted after each report.</p>
            <div className="field">
              <label className="field__label" htmlFor="resume">
                Resume (PDF, up to 5 MB)
              </label>
              <input
                className="input input--file"
                id="resume"
                name="resume"
                type="file"
                accept="application/pdf,.pdf"
                required
              />
            </div>
            <div className="row">
              <button type="submit" className="button button--soft">
                Upload and check
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel" aria-labelledby="delete-title">
        <div className="panel__head">
          <h2 className="panel__title" id="delete-title">
            Delete this check
          </h2>
        </div>
        <div className="panel__body stack stack--tight">
          <p className="note">Removes the candidate, every result and every stored file. This cannot be undone.</p>
          <div className="row">
            <Link href={`${path}/delete`} className="button button--ghost">
              Delete this check
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
