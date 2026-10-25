import type { Metadata } from "next";

import { RoleLogin } from "@/components/ui/RoleLogin";

export const metadata: Metadata = { title: "Organizer sign-in" };

export default async function OrganizerLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; mode?: string }>;
}) {
  const { error, mode } = await searchParams;
  return <RoleLogin role="organizer" error={error} mode={mode} />;
}
