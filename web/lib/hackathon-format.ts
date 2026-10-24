// Plain words for the organizer's pages. No ranking: lists are by team name, and "best" is always "up to three teams".
import type { Badge } from "@/lib/format";
import type { CardCheck, FlagLevel, OverviewProject } from "@/lib/types";

// Every status a hackathon project can carry (ai/talnex_ai/worker/subjects.py PROJECT_STATUSES, plus failed).
const PROJECT_STATUS: Record<string, Badge & { running: boolean }> = {
  submitted: { text: "Not checked yet", tone: "neutral", running: false },
  prechecking: { text: "Checking links", tone: "warning", running: true },
  reading: { text: "Reading the video", tone: "warning", running: true },
  testing: { text: "Testing", tone: "warning", running: true },
  checking: { text: "Checking the proof", tone: "warning", running: true },
  scoring: { text: "Scoring", tone: "warning", running: true },
  done: { text: "Done", tone: "success", running: false },
  done_with_gaps: { text: "Done with gaps", tone: "success", running: false },
  failed: { text: "Could not finish", tone: "danger", running: false },
};

export function projectStatus(status: string): Badge & { running: boolean } {
  return PROJECT_STATUS[status] ?? { text: "In progress", tone: "warning", running: true };
}

/** True while any project of the event is being checked, so the page keeps itself up to date. */
export function anyRunning(projects: Pick<OverviewProject, "status">[]): boolean {
  return projects.some((p) => projectStatus(p.status).running);
}

/** "1 strong · 2 to look at", or "None". Flags are counted beside the score, never taken from it. */
export function flagCountText(flags: Partial<Record<FlagLevel, number>>): string {
  const parts: string[] = [];
  if (flags.strong) parts.push(`${flags.strong} strong`);
  if (flags.review) parts.push(`${flags.review} to look at`);
  if (flags.info) parts.push(`${flags.info} for info`);
  return parts.length ? parts.join(" · ") : "None";
}

const GROUP_KINDS: Record<string, string> = {
  criterion: "Your criterion",
  standard: "Standard group",
  backend: "Backend group",
  other: "Other",
};

export function groupKindLabel(kind: string): string {
  return GROUP_KINDS[kind] ?? kind;
}

/** Which links a team gave, in words. */
export function linksGiven(p: Pick<OverviewProject, "has_video" | "has_live" | "has_repo">): string {
  const given = [p.has_live && "live site", p.has_repo && "repository", p.has_video && "video"].filter(Boolean);
  return given.length ? given.join(", ") : "no links";
}

/** "2 projects started, 1 already checked or being checked.", after "Check all projects". */
export function runAllText(started: number, skipped: number): string {
  if (started === 0 && skipped === 0) return "There are no projects to check yet.";
  const parts = [];
  if (started) parts.push(`${started} project${started === 1 ? "" : "s"} started`);
  if (skipped) parts.push(`${skipped} already checked or being checked`);
  return `${parts.join(", ")}.`;
}

/** One line of "checks that did not run". `stages` lists the checks folded into it, when several share one cause. */
export interface CheckRow {
  status: string;
  label: string;
  reason: string;
  stages?: string[];
}

// The checks that read or run a team's repository. Without a repository they all skip for the same reason.
const REPOSITORY_STAGES = /^(sandbox_|route_discovery|repo_|code_review|code_locate|authorship_|track_reconcile|tutorial_copy|github_)/;

/** The card's skipped and failed checks as a short list: a check that failed always gets its own line, and when the
 * team gave no repository, the repository checks become one line instead of a dozen. */
export function checkRows(checks: CardCheck[], hasRepo: boolean): CheckRow[] {
  const rows: CheckRow[] = [];
  const folded: string[] = [];
  for (const check of checks) {
    const label = check.stage.replace(/_/g, " ");
    const base = check.stage.split(":")[0].trim();
    if (!hasRepo && check.status !== "failed" && REPOSITORY_STAGES.test(base)) {
      folded.push(label);
      continue;
    }
    rows.push({ status: check.status, label, reason: check.reason ?? "" });
  }
  if (folded.length > 0) {
    rows.unshift({
      status: "skipped",
      label: "Repository checks",
      reason: "No repository link was given, so the code was not read or run.",
      stages: folded,
    });
  }
  return rows;
}
