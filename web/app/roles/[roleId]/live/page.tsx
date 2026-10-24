import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RoleLiveWall } from "@/components/live/RoleLiveWall";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { requireRole } from "@/lib/session";
import type { JobRole } from "@/lib/types";

export const metadata: Metadata = { title: "Watch the role live" };

const MAX_TILES = 24;

export default async function RoleLivePage({ params }: { params: Promise<{ roleId: string }> }) {
  await requireRole("recruiter");
  const { roleId } = await params;
  let role: JobRole;
  try {
    role = await apiFetch<JobRole>(`/v1/roles/${encodeURIComponent(roleId)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) notFound();
    throw error;
  }
  const all = role.candidates ?? [];
  const shown = all.slice(0, MAX_TILES).map((c) => ({ id: c.id, name: c.label || "Unnamed candidate" }));
  return (
    <div className="stack">
      <PageHeader
        title={`Live: ${role.title}`}
        lead={
          all.length > MAX_TILES
            ? `The first ${MAX_TILES} of ${all.length} candidates. Open a candidate for the full live view.`
            : "Every candidate as TalNex checks them. Open a tile for the full live view."
        }
        back={{ href: `/roles/${roleId}`, label: "Back to the role" }}
      />
      <RoleLiveWall candidates={shown} />
    </div>
  );
}
