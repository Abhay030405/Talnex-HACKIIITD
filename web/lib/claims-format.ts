// Resume vs GitHub (ai/talnex_ai/coding/claims_vs_github.py): the claimed date range and the commit range on one
// timeline. Positions and widths are in tenths, so the stylesheet draws them with fixed classes (no inline styles).
import type { ClaimsVsGithub } from "@/lib/types";

function month(value: string | null | undefined, end: boolean): number | null {
  if (!value) return null;
  if (value === "present") {
    const now = new Date();
    return now.getUTCFullYear() * 12 + now.getUTCMonth();
  }
  const year = Number(value.slice(0, 4));
  if (!Number.isFinite(year)) return null;
  const m = value.length >= 7 ? Number(value.slice(5, 7)) : end ? 12 : 1;
  return year * 12 + m - 1;
}

const label = (m: number) => `${Math.floor(m / 12)}-${String((m % 12) + 1).padStart(2, "0")}`;

/** [start tenth, width tenths] of each range on a shared axis, or null when either range is missing. */
export function claimsTimeline(claimed: ClaimsVsGithub["claimed"], actual: ClaimsVsGithub["actual"]) {
  const c0 = month(claimed.start, false);
  const c1 = month(claimed.end ?? claimed.start, true);
  const a0 = month(actual?.first_commit?.slice(0, 7), false);
  const a1 = month(actual?.last_commit?.slice(0, 7), true);
  if (c0 === null || c1 === null || a0 === null || a1 === null) return null;
  const lo = Math.min(c0, a0);
  const span = Math.max(Math.max(c1, a1) - lo + 1, 1);
  const place = (s: number, e: number): [number, number] => {
    const at = Math.min(9, Math.floor(((s - lo) / span) * 10));
    return [at, Math.max(1, Math.min(10 - at, Math.round(((e - s + 1) / span) * 10)))];
  };
  return { claimed: place(c0, c1), actual: place(a0, a1), from: label(lo), to: label(lo + span - 1) };
}
