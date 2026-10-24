import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { ConfirmForm } from "@/components/forms/ConfirmForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { getCandidateFound } from "@/lib/found";
import { requireRole } from "@/lib/session";
import { roleLabel } from "@/lib/types";

export const metadata: Metadata = { title: "Confirm what was found" };

export default async function ConfirmCandidatePage({ params }: { params: Promise<{ candidateId: string }> }) {
  const { candidateId } = await params;
  await requireRole("recruiter");

  const found = await getCandidateFound(candidateId);
  if (!found) notFound();
  // Only a check that is waiting can be confirmed; anything else belongs on the candidate page.
  if (found.status !== "awaiting_confirmation") redirect(`/candidates/${encodeURIComponent(candidateId)}`);

  return (
    <div className="stack">
      <PageHeader
        title="Confirm what was found"
        lead={`TalNex read the resume. Check the projects and coding profiles, fix anything wrong, then start the checks. Judged as ${roleLabel(found.role_level)}.`}
        back={{ href: `/candidates/${encodeURIComponent(candidateId)}`, label: "Back to the candidate" }}
      />
      <div className="card">
        <ConfirmForm candidateId={candidateId} found={found} />
      </div>
    </div>
  );
}
