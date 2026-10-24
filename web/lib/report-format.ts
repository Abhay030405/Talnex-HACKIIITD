// Plain words for the proof report. Shared with the hackathon proof card, so a feature reads the same on both.
// The rules of AGENTS.md section 8 show up here: "could not test" is neutral, never a failure; flags are labelled as
// sitting beside the score; code that was only read is always "reviewed from code, not run".
import type { Tone } from "@/lib/format";
import type {
  CandidateReport,
  Confidence,
  FlagLevel,
  ProjectStatus,
  ProofStep,
  ReportFeature,
  ReportFlag,
  Verdict,
} from "@/lib/types";

const VERDICTS: Record<Verdict, { text: string; tone: Tone }> = {
  works: { text: "Works", tone: "success" },
  partly_works: { text: "Partly works", tone: "warning" },
  broken: { text: "Broken", tone: "danger" },
  could_not_test: { text: "Could not test", tone: "neutral" },
  reviewed_from_code: { text: "Reviewed from code, not run", tone: "neutral" },
};

export function verdictInfo(verdict: Verdict | null): { text: string; tone: Tone } {
  return (verdict && VERDICTS[verdict]) || { text: "Not tested", tone: "neutral" };
}

const CONFIDENCE: Record<Confidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
  disagree: "Two checks disagreed, so this needs a human look",
};

export function confidenceLabel(confidence: Confidence | null): string {
  return (confidence && CONFIDENCE[confidence]) || "";
}

/** 7 and up is high, 4 to just under 7 medium, below 4 low. */
export function scoreLevel(score: number): "high" | "medium" | "low" {
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  return "low";
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return "–";
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

export function formatCoverage(coverage: number): string {
  return `${Math.round(Math.max(0, Math.min(100, coverage)))}%`;
}

const LEVEL_ORDER: Record<FlagLevel, number> = { strong: 0, review: 1, info: 2 };
const LEVEL_TEXT: Record<FlagLevel, string> = {
  strong: "Strong signal",
  review: "Worth a look",
  info: "For your information",
};
const LEVEL_TONE: Record<FlagLevel, Tone> = { strong: "danger", review: "warning", info: "neutral" };

export function flagLevelInfo(level: FlagLevel): { text: string; tone: Tone } {
  return { text: LEVEL_TEXT[level] ?? "For your information", tone: LEVEL_TONE[level] ?? "neutral" };
}

/** Strongest flags first; flags of the same strength keep their order. Does not change the input. */
export function sortFlags(flags: ReportFlag[]): ReportFlag[] {
  return [...flags].sort((a, b) => (LEVEL_ORDER[a.level] ?? 3) - (LEVEL_ORDER[b.level] ?? 3));
}

export interface FlagGroup {
  type: string;
  level: FlagLevel;
  reasons: string[];
}

/** Flags of one kind folded into one line, so "Feature arrived in one drop" shows once with every feature it covers,
 * not once per feature. The group takes its strongest level; groups come strongest first. */
export function groupFlags(flags: ReportFlag[]): FlagGroup[] {
  const groups = new Map<string, FlagGroup>();
  for (const flag of sortFlags(flags)) {
    const group = groups.get(flag.type);
    if (group) group.reasons.push(flag.reason);
    else groups.set(flag.type, { type: flag.type, level: flag.level, reasons: [flag.reason] });
  }
  return [...groups.values()];
}

const SUMMARY_ORDER: [Verdict, string][] = [
  ["works", "works"],
  ["partly_works", "partly works"],
  ["broken", "broken"],
  ["reviewed_from_code", "reviewed from code"],
  ["could_not_test", "could not test"],
];

/** One line on how a project's claims came out: "4 works · 1 broken · 2 could not test". */
export function verdictSummary(features: ReportFeature[]): string {
  const counts = new Map<string, number>();
  for (const f of features) counts.set(f.verdict ?? "could_not_test", (counts.get(f.verdict ?? "could_not_test") ?? 0) + 1);
  return SUMMARY_ORDER.filter(([v]) => counts.get(v)).map(([v, words]) => `${counts.get(v)} ${words}`).join(" · ");
}

/** Claims that were tested, and those that could not be, each keeping its order. */
export function splitTested(features: ReportFeature[]): { tested: ReportFeature[]; untested: ReportFeature[] } {
  const untested = (f: ReportFeature) => !f.verdict || f.verdict === "could_not_test";
  return { tested: features.filter((f) => !untested(f)), untested: features.filter(untested) };
}

const FLAG_TYPES: Record<string, string> = {
  hidden_ai_instructions: "Hidden instructions aimed at an AI checker",
  leaked_secret: "The live site leaks a secret or private data",
  required_item_missing: "Required item missing",
  code_before_event: "Code written before the event",
  event_dates: "Event dates",
  repo_vs_live: "Repository and live site differ",
  tutorial_copy: "Possible tutorial or template copy",
  copy_between_teams: "Code shared with another team",
  copied_from_team: "Code shared with another team",
  sponsor_tech_not_used: "Sponsor tool not used",
  sponsor_tools: "Sponsor tools",
  sponsor_files: "Sponsor tools",
  authorship: "Who wrote the code",
  feature_one_drop: "Feature arrived in one drop",
  one_drop: "Feature arrived in one drop",
  feature_before_event: "Feature built before the event",
  claimed_by_other_account: "Claimed feature written by another account",
  reformatting_hides_authorship: "Reformatting hides who wrote it",
};

/** A flag type the website does not know yet still reads as words. */
export function flagTypeLabel(type: string): string {
  return FLAG_TYPES[type] ?? type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

const PROJECT_STATUS: Record<ProjectStatus, { text: string; tone: Tone }> = {
  tested: { text: "Tested", tone: "success" },
  could_not_test: { text: "Could not test", tone: "neutral" },
  no_live_link: { text: "No live link", tone: "neutral" },
};

export function projectStatusInfo(status: ProjectStatus): { text: string; tone: Tone } {
  return PROJECT_STATUS[status] ?? { text: status.replace(/_/g, " "), tone: "neutral" };
}

export const SITE_NAMES: Record<string, string> = {
  codeforces: "Codeforces",
  leetcode: "LeetCode",
  codechef: "CodeChef",
  github: "GitHub",
};

// The weights the database allows (backend/migrations: coding_signals.weight).
const SIGNAL_WEIGHTS: Record<string, { text: string; tone: Tone }> = {
  not_suspicious: { text: "Not suspicious", tone: "neutral" },
  medium: { text: "Worth a look", tone: "warning" },
  strong: { text: "Strong signal", tone: "danger" },
};

export function signalWeightInfo(weight: string): { text: string; tone: Tone } {
  return SIGNAL_WEIGHTS[weight] ?? { text: weight.replace(/_/g, " "), tone: "neutral" };
}

/** Evidence as label and value pairs: "max_rating" becomes "Max rating"; lists and objects become short text. */
export function evidenceFacts(evidence: Record<string, unknown>): { label: string; value: string }[] {
  return Object.entries(evidence ?? {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([key, value]) => {
      const label = key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
      let text: string;
      if (typeof value === "boolean") text = value ? "yes" : "no";
      else if (Array.isArray(value))
        text = value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ");
      else if (typeof value === "object") text = JSON.stringify(value);
      else text = String(value);
      return { label, value: text.length > 300 ? `${text.slice(0, 300)}…` : text };
    });
}

export function reportSummary(report: CandidateReport) {
  const features = report.projects.flatMap((p) => p.features.filter((f) => f.testable));
  return {
    projectsTested: report.projects.filter((p) => p.status === "tested").length,
    projectsTotal: report.projects.length,
    featuresScored: features.filter((f) => f.score10 !== null).length,
    featuresTotal: features.length,
  };
}

/** What a step's proof file is, so a backend answer is offered as a link and never shown as a broken picture. */
export function proofInfo(step: ProofStep): { show: "image" | "link" | "none"; text: string } {
  if (!step.proof_url) return { show: "none", text: "No proof file was saved for this step." };
  if (step.kind === "screen") return { show: "image", text: `Screenshot for step ${step.step}` };
  if (step.kind === "http") return { show: "link", text: "Open the saved request and answer" };
  return { show: "link", text: "Open the saved command output" };
}

const STATUS_WORDS: Record<string, string> = {
  submitted: "Received. Waiting to start reading the resume.",
  reading: "Reading the resume and finding the projects.",
  awaiting_confirmation: "The resume was read. Waiting for you to confirm the projects and coding profiles.",
  prechecking: "Checking the project links and repositories.",
  testing: "Using each live project like a real person.",
  reporting: "Putting the proof report together.",
  done: "Finished.",
  done_with_gaps: "Finished. Some parts could not be tested; they do not count against the candidate.",
  failed: "The check could not finish. Upload the resume again to retry.",
};

export function statusWords(status: string): string {
  return STATUS_WORDS[status] ?? "Working on it.";
}

export interface ClipFrame {
  url: string;
  caption: string;
  seen: string | null;
}

/** A claim's run as a short clip: its screenshots in order, ending on the verdict. */
export interface ProofClipData {
  frames: ClipFrame[];
  stamp: { text: string; tone: Tone };
}

/** The clip for one claim, or null when fewer than two screenshots were saved (nothing to play). */
export function proofClip(steps: ProofStep[], verdict: Verdict | null): ProofClipData | null {
  const frames = steps
    .filter((s) => s.kind === "screen" && s.proof_url)
    .map((s) => ({ url: s.proof_url as string, caption: `Step ${s.step}: ${s.action}`, seen: s.observed }));
  return frames.length < 2 ? null : { frames, stamp: verdictInfo(verdict) };
}
