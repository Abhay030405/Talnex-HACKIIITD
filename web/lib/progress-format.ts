// Plain words for the progress panel. The API already sends the stages in the order they happen
// (backend/internal/candidates/progress.go), so they are shown as they come.
import type { StageState } from "@/lib/types";
import type { Tone } from "@/lib/format";

const STAGE_LABELS: Record<string, string> = {
  resume_read: "Reading the resume",
  github_profile: "Reading the GitHub profile",
  codeforces: "Coding profile: Codeforces",
  codechef: "Coding profile: CodeChef",
  leetcode: "Coding profile: LeetCode",
  candidate_report: "Writing the report",
  resume_cleanup: "Deleting the resume",
  precheck: "Checking the links",
  claims: "Finding what it claims",
  github_check: "Reading the repository",
  test_plan: "Planning the tests",
  live_test: "Testing the live site",
  proof_check: "Checking the proof",
  feature_score: "Scoring the features",
  originality: "Originality checks",
  project_summary: "Wrapping up",
};

/** A stage the website does not know yet still gets readable words, never a raw name. */
export function stageLabel(name: string): string {
  return STAGE_LABELS[name] ?? name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

const STATES: Record<StageState, { text: string; tone: Tone }> = {
  waiting: { text: "Waiting", tone: "neutral" },
  running: { text: "Running", tone: "warning" },
  retrying: { text: "Trying again", tone: "warning" },
  done: { text: "Done", tone: "success" },
  // "Could not finish", never "failed": a stage that did not finish is not a verdict on the candidate.
  failed: { text: "Could not finish", tone: "danger" },
};

export function stageState(state: string): { text: string; tone: Tone } {
  return STATES[state as StageState] ?? STATES.waiting;
}

const FINISHED = new Set(["done", "done_with_gaps", "failed"]);

/** True when nothing more will happen, so the page can stop refreshing itself. */
export function isFinishedStatus(status: string): boolean {
  return FINISHED.has(status);
}

const CAN_CHECK_AGAIN = new Set(["submitted", "failed", "done", "done_with_gaps"]);

/** Whether a new resume can be sent now. The API refuses one while a resume is still being read. */
export function canUploadResume(status: string): boolean {
  return CAN_CHECK_AGAIN.has(status);
}
