import type { Metadata } from "next";

import { RoleLogin } from "@/components/ui/RoleLogin";

export const metadata: Metadata = { title: "Organizer sign-in" };

export default async function OrganizerLoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  return <RoleLogin role="organizer" error={(await searchParams).error} />;
}
