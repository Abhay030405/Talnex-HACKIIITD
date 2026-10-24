import type { Metadata } from "next";

import { RoleLogin } from "@/components/ui/RoleLogin";

export const metadata: Metadata = { title: "Recruiter sign-in" };

export default async function RecruiterLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; mode?: string }>;
}) {
  const { error, mode } = await searchParams;
  return <RoleLogin role="recruiter" error={error} mode={mode} />;
}
