"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import { parseRoleForm } from "@/lib/role-form";

export interface SettingsState {
  error?: string;
  saved?: boolean;
}

/** Save the role's brief, criteria, weights and checks. Results stay; every report re-scores with the new weights. */
export async function updateRole(roleId: string, _previous: SettingsState, form: FormData): Promise<SettingsState> {
  const parsed = parseRoleForm(form);
  if (!parsed.ok) return { error: parsed.error };
  try {
    await apiFetch(`/v1/roles/${encodeURIComponent(roleId)}`, { method: "PUT", body: parsed.value });
  } catch (error) {
    return { error: error instanceof ApiError && error.status < 500 ? error.message : "We could not save the role." };
  }
  revalidatePath(`/roles/${roleId}`);
  return { saved: true };
}
