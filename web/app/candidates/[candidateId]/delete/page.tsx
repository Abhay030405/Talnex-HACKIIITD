import type { Metadata } from "next";
import Link from "next/link";
import { notFound, unstable_rethrow } from "next/navigation";

import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { requireRole } from "@/lib/session";
import type { CandidateSummary } from "@/lib/types";

import { deleteCandidateAction } from "../actions";

export const metadata: Metadata = { title: "Delete this check" };

const ERRORS: Record<string, string> = {
  busy: "This check is still running. Wait for it to finish, then try again.",
  failed: "We could not delete this check. Please try again.",
};

/** A separate page to confirm, so a delete is never one stray click. */
export default async function DeleteCandidatePage({
  params,
  searchParams,
}: {
  params: Promise<{ candidateId: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const { candidateId } = await params;
  const { error } = await searchParams;
  await requireRole("recruiter");

  let candidate: CandidateSummary;
  try {
    candidate = await apiFetch<CandidateSummary>(`/v1/candidates/${encodeURIComponent(candidateId)}`);
  } catch (caught) {
    unstable_rethrow(caught);
    if (caught instanceof ApiError && (caught.status === 404 || caught.status === 400)) notFound();
    throw caught;
  }
  const back = `/candidates/${encodeURIComponent(candidateId)}`;

  return (
    <div className="stack">
      <PageHeader title="Delete this check" back={{ href: back, label: "Back to the candidate" }} />

      {error && ERRORS[error] && (
        <p className="form-error" role="alert">
          {ERRORS[error]}
        </p>
      )}

      <section className="panel" aria-labelledby="delete-name">
        <div className="panel__head">
          <h2 className="panel__title" id="delete-name">
            {candidate.label || "Unnamed candidate"}
          </h2>
        </div>
        <div className="panel__body stack stack--tight">
          <p>This removes the candidate, every result, all flags and every screenshot. It cannot be undone.</p>
          <form action={deleteCandidateAction.bind(null, candidateId)} className="row">
            <button type="submit" className="button button--danger">
              Delete for good
            </button>
            <Link href={back} className="button button--ghost">
              Keep it
            </Link>
          </form>
        </div>
      </section>
    </div>
  );
}
