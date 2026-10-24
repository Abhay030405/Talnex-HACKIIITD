// Turns the confirm form into what POST /v1/candidates/{id}/confirm takes, with the API's own rules
// (backend/internal/candidates/confirm.go) checked first, so a mistake is explained before anything is sent.
import { PROFILE_KINDS, profileLinksFrom } from "@/lib/profile-links";
import type { CandidateConfirm, FoundProject } from "@/lib/types";

export const CODING_SITES = [
  { key: "codeforces", label: "Codeforces", example: "https://codeforces.com/profile/handle" },
  { key: "leetcode", label: "LeetCode", example: "https://leetcode.com/u/handle" },
  { key: "codechef", label: "CodeChef", example: "https://www.codechef.com/users/handle" },
] as const;

/** The most projects the API checks in one go, and the longest project name it takes. */
export const MAX_PROJECTS = 8;
export const MAX_NAME_CHARS = 120;

const FIELD = /^project\.(\d+)\.(id|name|live_url|repo_url|video_url)$/;

export type ParsedConfirm = { ok: true; value: CandidateConfirm } | { ok: false; error: string };

/**
 * Projects arrive as `project.<n>.<field>`. The numbers only keep rows apart, so gaps from removed rows are fine.
 * A row left completely empty is ignored. Every coding site is always sent: an empty one removes that profile.
 */
export function parseConfirmForm(form: FormData): ParsedConfirm {
  const rows = new Map<number, Record<string, string>>();
  for (const [key, value] of form.entries()) {
    const match = FIELD.exec(key);
    if (!match || typeof value !== "string") continue;
    const index = Number(match[1]);
    rows.set(index, { ...rows.get(index), [match[2]]: value.trim() });
  }

  const projects: FoundProject[] = [...rows.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, row]) => row)
    .filter((row) => Object.entries(row).some(([field, value]) => field !== "id" && value !== ""))
    .map((row) => ({
      ...(row.id ? { id: row.id } : {}),
      // The API squeezes repeated spaces the same way, so the duplicate check below matches its own.
      name: (row.name ?? "").replace(/\s+/g, " "),
      live_url: row.live_url ?? "",
      repo_url: row.repo_url ?? "",
      video_url: row.video_url ?? "",
    }));

  if (projects.length === 0) return { ok: false, error: "Add at least one project to check." };
  if (projects.length > MAX_PROJECTS) return { ok: false, error: `Check at most ${MAX_PROJECTS} projects at once.` };
  const seen = new Set<string>();
  for (const p of projects) {
    if (!p.name) return { ok: false, error: "Every project needs a name." };
    if ([...p.name].length > MAX_NAME_CHARS)
      return { ok: false, error: `“${p.name.slice(0, 40)}…” is too long a name.` };
    if (seen.has(p.name.toLowerCase())) return { ok: false, error: `Two projects are called “${p.name}”.` };
    seen.add(p.name.toLowerCase());
  }

  const coding_profiles: Record<string, string> = {};
  for (const site of CODING_SITES) coding_profiles[site.key] = String(form.get(`profile.${site.key}`) ?? "").trim();
  // Only sent when the form has the link boxes, so an older form never wipes the saved links.
  const profile_links = form.has(`link.${PROFILE_KINDS[0].key}`) ? profileLinksFrom(form) : undefined;
  return { ok: true, value: { projects, coding_profiles, ...(profile_links ? { profile_links } : {}) } };
}

/** What a profile box starts with: the link as written on the resume, else the handle. */
export function profileValue(site: string, links: Record<string, string>, handles: Record<string, string>): string {
  return links?.[site] || handles?.[site] || "";
}
