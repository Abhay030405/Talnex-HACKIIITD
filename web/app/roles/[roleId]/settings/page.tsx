import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RoleSettingsForm } from "@/components/forms/RoleSettingsForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { requireRole } from "@/lib/session";
import type { JobRole } from "@/lib/types";

export const metadata: Metadata = { title: "Role settings" };

export default async function RoleSettingsPage({ params }: { params: Promise<{ roleId: string }> }) {
  await requireRole("recruiter");
  const { roleId } = await params;
  let role: JobRole;
  try {
    role = await apiFetch<JobRole>(`/v1/roles/${encodeURIComponent(roleId)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) notFound();
    throw error;
  }
  return (
    <div className="stack">
      <PageHeader
        title={`Settings: ${role.title}`}
        lead="Change the brief, criteria and weights before or after results. Weights re-score every candidate at once."
        back={{ href: `/roles/${roleId}`, label: "Back to the role" }}
      />
      <div className="card">
        <RoleSettingsForm role={role} />
      </div>
    </div>
  );
}
