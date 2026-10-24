// How things are shown in words: dates, statuses and the counts on the workspace pages.
import type { CandidateSummary, EventState } from "@/lib/types";

/** "4 Nov 2026". Dates are shown in UTC, the way the API stores them, so everyone sees the same day. */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** "4 – 6 Nov 2026", or the full dates when they span months or years. */
export function formatDateRange(startIso: string, endIso: string): string {
  const start = new Date(startIso);
  const end = new Date(endIso);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "—";
  const sameMonth = start.getUTCFullYear() === end.getUTCFullYear() && start.getUTCMonth() === end.getUTCMonth();
  if (sameMonth && start.getUTCDate() === end.getUTCDate()) return formatDate(endIso);
  return sameMonth
    ? `${start.getUTCDate()} – ${formatDate(endIso)}`
    : `${formatDate(startIso)} – ${formatDate(endIso)}`;
}

export type Tone = "success" | "warning" | "danger" | "neutral" | "action";

/** What a badge says and how it looks. */
export interface Badge {
  text: string;
  tone: Tone;
}

export const BADGE_CLASS: Record<Tone, string> = {
  success: "badge badge--success",
  warning: "badge badge--warning",
  danger: "badge badge--danger",
  neutral: "badge badge--neutral",
  action: "badge",
};

export type CandidateStage = "needs_you" | "working" | "finished" | "failed";

// Every status the backend and the AI workers set on a candidate (backend/internal/candidates, ai worker handlers).
const CANDIDATE_STATUS: Record<string, Badge & { stage: CandidateStage }> = {
  submitted: { text: "Queued", tone: "warning", stage: "working" },
  reading: { text: "Reading resume", tone: "warning", stage: "working" },
  awaiting_confirmation: { text: "Needs your check", tone: "action", stage: "needs_you" },
  prechecking: { text: "Checking links", tone: "warning", stage: "working" },
  testing: { text: "Testing", tone: "warning", stage: "working" },
  reporting: { text: "Writing report", tone: "warning", stage: "working" },
  done: { text: "Done", tone: "success", stage: "finished" },
  done_with_gaps: { text: "Done with gaps", tone: "success", stage: "finished" },
  failed: { text: "Failed", tone: "danger", stage: "failed" },
};

/** A status the website does not know yet still shows, as work in progress, instead of breaking the page. */
export function candidateStatus(status: string): Badge & { stage: CandidateStage } {
  return CANDIDATE_STATUS[status] ?? { text: "In progress", tone: "warning", stage: "working" };
}

export function countByStage(candidates: Pick<CandidateSummary, "status">[]): Record<CandidateStage, number> {
  const counts: Record<CandidateStage, number> = { needs_you: 0, working: 0, finished: 0, failed: 0 };
  for (const c of candidates) counts[candidateStatus(c.status).stage]++;
  return counts;
}

export const EVENT_STATE_BADGE: Record<EventState, Badge> = {
  live: { text: "Live now", tone: "success" },
  upcoming: { text: "Upcoming", tone: "warning" },
  ended: { text: "Ended", tone: "neutral" },
};

/** A check's length the way a person says it: "42 s", "4 min 41 s", "1 h 3 min". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) {
    const rest = s % 60;
    return `${Math.floor(s / 60)} min${rest ? ` ${rest} s` : ""}`;
  }
  const minutes = Math.floor((s % 3600) / 60);
  return `${Math.floor(s / 3600)} h${minutes ? ` ${minutes} min` : ""}`;
}

/** Dollars: cents for normal amounts, four places for tiny ones so a $0.0026 browser session isn't shown as $0.00. */
export function formatCost(usd: number): string {
  if (usd > 0 && usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** One line for a check's time and cost, with model and browser apart. */
export function runLine(run: { seconds: number; finished: boolean; cost_usd: number; model_usd: number; browser_usd: number }): string {
  const time = `${run.finished ? "Checked in" : "Running for"} ${formatDuration(run.seconds)}`;
  return `${time} · ${formatCost(run.cost_usd)} (model ${formatCost(run.model_usd)} · browser ${formatCost(run.browser_usd)})`;
}
