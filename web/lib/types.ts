// Shapes the Go API sends and receives, checked against backend/internal/{auth,events,projects,candidates}.
// The report, proof card, authorship and walkthrough shapes are added with the pages that show them.

// ---------- Roles ----------

/** Who an account is. One role per account, set by the sign-in door used first (backend/internal/auth). */
export type Role = "recruiter" | "organizer";

export const ROLES: readonly Role[] = ["recruiter", "organizer"];

export function isRole(value: unknown): value is Role {
  return value === "recruiter" || value === "organizer";
}

/** The workspace home page of a role. */
export function homePath(role: Role): string {
  return role === "recruiter" ? "/recruiter" : "/organizer";
}

export const ROLE_NAMES: Record<Role, string> = { recruiter: "Recruiter", organizer: "Hackathon organizer" };

// ---------- Role level: how strictly a project is judged ----------

export type RoleLevel = "fresher" | "junior" | "mid" | "senior";

export const ROLE_LEVELS: readonly { value: RoleLevel; label: string; hint: string }[] = [
  { value: "fresher", label: "Fresher", hint: "Judged on how it is implemented, not on design" },
  { value: "junior", label: "Junior", hint: "Light weight on design and structure" },
  { value: "mid", label: "Mid", hint: "Design and edge cases both count" },
  { value: "senior", label: "Senior", hint: "Design and structure weigh the most" },
];

export function roleLabel(level: RoleLevel): string {
  return ROLE_LEVELS.find((r) => r.value === level)?.label ?? level;
}

// ---------- Hackathon events and projects ----------

export type EventMode = "open_theme" | "fixed_problem";

export function modeLabel(mode: EventMode): string {
  return mode === "open_theme" ? "Open theme" : "Fixed problem";
}

/** One scoring criterion of a fixed-problem event. Weights are shown as given; the total is labelled weighted. */
export interface Criterion {
  id: string;
  name: string;
  description: string;
  weight: number;
}

export interface EventSummary {
  id: string;
  name: string;
  mode: EventMode;
  role_level: RoleLevel;
  starts_at: string;
  ends_at: string;
  sponsor_tools: string[];
  /** Fixed-problem events only. Lists may leave it out or send null. */
  criteria?: Criterion[] | null;
  created_at: string;
}

export type EventState = "upcoming" | "live" | "ended";

/** Where an event is in time. The API stores the end date as the end of its last day. */
export function eventState(event: Pick<EventSummary, "starts_at" | "ends_at">, now: Date = new Date()): EventState {
  if (now < new Date(event.starts_at)) return "upcoming";
  if (now > new Date(event.ends_at)) return "ended";
  return "live";
}

export interface ProjectSummary {
  id: string;
  event_id: string;
  team_name: string;
  video_url: string;
  live_url: string;
  repo_url: string;
  /** A name in TinyFish Vault, never a password: test logins never go in our database. */
  test_login_ref: string;
  team_github_handles: string[];
  status: string;
  status_detail: string;
  created_at: string;
  updated_at: string;
}

// ---------- Recruiter candidates ----------

export interface CandidateSummary {
  id: string;
  label: string;
  role_level: RoleLevel;
  coding_handles: Record<string, string>;
  status: string;
  created_at: string;
}

/** One project as the resume reader found it, for the recruiter to confirm or fix. */
export interface FoundProject {
  id?: string;
  name: string;
  live_url: string;
  repo_url: string;
  video_url: string;
  /** Read only: the resume lines this project came from. */
  bullets?: string[];
}

/** What the resume reader found. The check waits until the recruiter confirms it. */
export interface CandidateFound {
  status: string;
  status_detail: string;
  role_level: RoleLevel;
  projects: FoundProject[];
  coding_handles: Record<string, string>;
  coding_links: Record<string, string>;
}

/** What the recruiter sends back. A coding profile left empty is removed. */
export interface CandidateConfirm {
  projects: FoundProject[];
  coding_profiles: Record<string, string>;
}

// ---------- Live progress ----------

export type StageState = "waiting" | "running" | "retrying" | "done" | "failed";

export interface ProgressStage {
  name: string;
  state: StageState;
  note?: string;
}

export interface ProgressProject {
  id: string;
  name: string;
  stages: ProgressStage[];
}

export interface CandidateProgress {
  status: string;
  status_detail: string;
  stages: ProgressStage[];
  projects: ProgressProject[];
  report_ready: boolean;
}

// ---------- The recruiter proof report ----------
// Built by ai/talnex_ai/reports/recruiter_report.py and proof.py; the API swaps each step's storage key for a short-lived
// proof_url (backend/internal/http/report.go). Allowed values follow the CHECK rules in backend/migrations.

export type Verdict = "works" | "partly_works" | "broken" | "could_not_test" | "reviewed_from_code";
export type Confidence = "high" | "medium" | "low" | "disagree";
export type FlagLevel = "info" | "review" | "strong";
export type ProjectStatus = "tested" | "could_not_test" | "no_live_link";
/** screen: a screenshot. http: a saved request and answer (backend test). command: a saved command's output. */
export type ProofKind = "screen" | "http" | "command";

export interface ProofStep {
  step: number;
  action: string;
  observed: string | null;
  kind: ProofKind;
  test_type?: string | null;
  track?: string | null;
  /** Missing when there is no proof file or no link could be made. */
  proof_url?: string;
}

/** What reading the code found for a claim that was not run. Always shown as "reviewed from code, not run". */
export interface CodeReview {
  label: string;
  mechanism: string | null;
  summary: string | null;
  evidence: unknown[];
  quality: unknown[];
  files_read: string[];
}

export interface ReportFeature {
  claim_id: string;
  text: string;
  group: string | null;
  importance: number;
  testable: boolean;
  untestable_reason: string | null;
  track?: string | null;
  source?: string | null;
  verdict: Verdict | null;
  confidence: Confidence | null;
  reason: string | null;
  score10: number | null;
  score_reason: string | null;
  proof: ProofStep[];
  code_review?: CodeReview | null;
}

export interface ReportFlag {
  type: string;
  level: FlagLevel;
  reason: string;
}

export interface ProjectTalnex {
  score10: number | null;
  coverage: number;
  features_scored: number;
  features_total: number;
  low_coverage: boolean;
}

export interface ProjectOriginality {
  repo_found: boolean;
  created_at: string | null;
  pushed_at: string | null;
  fork: boolean;
  languages: Record<string, number>;
  notes: string[];
}

export interface ReportProject {
  id: string;
  name: string;
  live_url: string | null;
  repo_url: string | null;
  status: ProjectStatus;
  status_reason: string;
  talnex: ProjectTalnex | null;
  features: ReportFeature[];
  flags: ReportFlag[];
  originality: ProjectOriginality | null;
}

export interface CodingSignal {
  site: "codeforces" | "leetcode" | "codechef" | "github" | string;
  signal: string;
  weight: "not_suspicious" | "medium" | "strong" | string;
  contest: string | null;
  evidence: Record<string, unknown>;
}

export interface CandidateReport {
  version: number;
  candidate_id: string;
  generated_at: string;
  role_level: RoleLevel;
  has_gaps: boolean;
  time_saved: { manual_minutes_estimate: number; talnex_minutes: number; saved_minutes: number };
  projects: ReportProject[];
  coding_signals: CodingSignal[];
  flags: ReportFlag[];
  notes: string[];
}

