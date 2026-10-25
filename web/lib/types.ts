// Shapes the Go API sends and receives, checked against backend/internal/{auth,events,projects,candidates}.
// The report, proof card, authorship and walkthrough shapes are added with the pages that show them.

// ---------- Jobs ----------

/** One job of a check, for the jobs panel (backend/internal/http/jobs.go). */
export interface JobRow {
  id: string;
  pipeline: string;
  stage: string;
  target_type: "candidate" | "candidate_project" | "project" | "event";
  target_id: string;
  /** The resume project's name, for jobs about a resume project. */
  project?: string;
  run: number;
  status: "queued" | "running" | "retrying" | "done" | "failed";
  tries: number;
  max_tries: number;
  created_at: string;
  updated_at: string;
  seconds: number;
  error?: string;
  result?: Record<string, unknown>;
  /** The stages this one waits for, to draw the pipeline. */
  after_stages?: string[];
}

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
  /** Set when the candidate was uploaded under a role (a job opening). */
  role_id?: string;
  coding_handles: Record<string, string>;
  coding_links?: Record<string, string>;
  /** Profile pages from the resume (links only, never email or phone). */
  profile_links?: Record<string, string>;
  status: string;
  created_at: string;
}

/** Checks a role can switch on or off (backend/internal/candidates/roles.go). Empty means every check. */
export const ROLE_CHECKS = [
  { value: "live_test", label: "Live test", hint: "Use each live project like a real person" },
  { value: "code_review", label: "Code review and authorship", hint: "Read the code and who wrote it" },
  { value: "coding_profiles", label: "Coding profiles", hint: "Codeforces, LeetCode (with replay pastes), CodeChef" },
  { value: "linkedin", label: "LinkedIn", hint: "Check the LinkedIn profile exists and whose it is" },
] as const;
export type RoleCheck = (typeof ROLE_CHECKS)[number]["value"];

/** A job opening: what the recruiter is hiring for, shared by every resume uploaded to it. */
export interface JobRole {
  id: string;
  title: string;
  job_description: string;
  person_wanted: string;
  skills: string[];
  role_level: RoleLevel;
  criteria: { name: string; description: string; weight: number }[] | null;
  checks: Partial<Record<RoleCheck, boolean>>;
  auto_confirm: boolean;
  candidate_count: number;
  created_at: string;
  /** Only when one role is read. */
  candidates?: CandidateSummary[];
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
  /** What the resume says about when and by whom it was built (YYYY or YYYY-MM; the end may be "present"). */
  claimed_start?: string;
  claimed_end?: string;
  claimed_team?: "" | "solo" | "team";
  claimed_team_size?: number;
  claimed_role?: string;
}

/** What the resume reader found. The check waits until the recruiter confirms it. */
export interface CandidateFound {
  status: string;
  status_detail: string;
  role_level: RoleLevel;
  projects: FoundProject[];
  coding_handles: Record<string, string>;
  coding_links: Record<string, string>;
  /** GitHub, LinkedIn, portfolio, ... from the resume: kind -> address. Links only, never email or phone. */
  profile_links?: Record<string, string>;
}

/** What the recruiter sends back. A coding profile left empty is removed. */
export interface CandidateConfirm {
  projects: FoundProject[];
  coding_profiles: Record<string, string>;
  /** Replaces the profile links (kind -> address; empty removes it). */
  profile_links?: Record<string, string>;
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

/** What the browser's developer tools saw during one step (ai/talnex_ai/testing/runner/devtools.py). */
export interface DevtoolsRecord {
  api_calls?: { method: string; url: string; status: number; ms?: number }[];
  error_responses?: { method: string; url: string; status: number; ms?: number }[];
  failed_requests?: { method: string; url: string; error: string }[];
  console_errors?: string[];
  page_errors?: string[];
  slow_api_calls?: number;
  /** Secrets or private data the site showed, masked: never the secret itself. */
  leaks?: { type: string; level: string; masked: string; where: string }[];
}

export interface ProofStep {
  devtools?: DevtoolsRecord | null;
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
  /** Who wrote the code behind this claim. Missing on reports made before authorship existed. */
  authorship?: Authorship | null;
  /** What TalNex planned to check, written before testing. */
  checklist?: string[];
  /** True when the checklist was written with the recruiter's role brief. */
  checked_for_role?: boolean;
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
  /** What the VM track did with the repository (ai/talnex_ai/reports/sandbox.py). Missing on older reports. */
  sandbox?: SandboxFacts | null;
  /** What the resume says about the project beside its GitHub history (coding/claims_vs_github.py). */
  claims_vs_github?: ClaimsVsGithub | null;
  /** Engineering quality, when another stage adds it; shown in the Repository tab if present. */
  engineering?: Record<string, unknown> | null;
}

/** The VM (sandbox) facts of one project. Log keys arrive from the API as short-lived links. */
export interface SandboxFacts {
  ran: boolean;
  reason?: string;
  status?: string;
  detail?: string | null;
  stack?: string | null;
  recipe_source?: string | null;
  needed_a_fix?: boolean;
  notes?: string[];
  routes_found?: number;
  spec_found?: boolean;
  no_live_link?: boolean;
  build_log_url?: string;
  run_log_url?: string;
  /** Each sandbox stage's saved result, kept small (scalars and counts). */
  stages?: Record<string, Record<string, unknown>>;
}

export interface CodingSignal {
  site: "codeforces" | "leetcode" | "codechef" | "github" | string;
  signal: string;
  weight: "not_suspicious" | "medium" | "strong" | string;
  contest: string | null;
  /** The contest problem, for per-problem signals such as a LeetCode paste. */
  problem?: string | null;
  evidence: Record<string, unknown>;
}

export interface CandidateReport {
  version: number;
  candidate_id: string;
  generated_at: string;
  role_level: RoleLevel;
  has_gaps: boolean;
  time_saved: { manual_minutes_estimate: number; talnex_minutes: number; saved_minutes: number };
  run?: RunUsage | null;
  projects: ReportProject[];
  coding_signals: CodingSignal[];
  flags: ReportFlag[];
  notes: string[];
  /** Plain-words readings of the coding signals, each a strength, neutral or worth a look. Never scored. */
  profile_insights?: CodingSignal[];
  /** True while some projects are still being checked: results so far. */
  partial?: boolean;
  /** The role the candidate was checked for, with each must-have skill and the working features that show it. */
  role?: { title: string; skills: { skill: string; proven_by: string[] }[] } | null;
  /** Questions to ask the candidate, each tied to its proof. Missing on reports made before the kit existed. */
  interview_kit?: InterviewQuestion[];
}

/** One interview question from ai/talnex_ai/reports/interview_kit.py. A thing to talk about, never a verdict. */
export interface InterviewQuestion {
  kind: "coding" | "feature" | "flag" | "demo" | "skill";
  question: string;
  why: string;
  proof: Record<string, string | null | undefined>;
}

// ---------- The hackathon proof card, overview and compare ----------
// Built by ai/talnex_ai/reports/project_card.py and scoring/feature_compare; served by backend/internal/http/proof.go,
// which swaps storage keys for short-lived links.

export interface CardGroup {
  group: string;
  kind: "standard" | "backend" | "other" | "criterion" | string;
  score: number | null;
  coverage: number;
  confidence: string | null;
  claims_used: number;
  low_coverage: boolean;
}

/** Fixed-problem events only: the total over the organizer's criteria, always shown with its label. */
export interface WeightedTotal {
  score: number | null;
  weight_covered: number;
  criteria_used: number;
  criteria_total: number;
  label: string;
}

export interface OpinionPart {
  part: string;
  score: number | null;
  scores: (number | null)[];
  disagree: boolean;
  reason: string;
  proof_url?: string;
}

/** Never part of any score, and always labelled "AI opinion — not tested proof". */
export interface AiOpinion {
  label: string;
  ui: { parts: OpinionPart[]; disagreement_note: string | null } | null;
  innovation: { parts: OpinionPart[]; disagreement_note: string | null } | null;
  ui_note?: string;
  models: string[];
}

/** How long a check took and what it cost, from the jobs and the usage log. Model and browser costs are apart. */
export interface RunUsage {
  seconds: number;
  finished: boolean;
  cost_usd: number;
  model_usd: number;
  browser_usd: number;
  model_calls: number;
  browser_sessions: number;
}

export interface CardCheck {
  stage: string;
  status: string;
  reason?: string | null;
}

export interface HackathonCard {
  version: number;
  project_id: string;
  generated_at: string;
  team_name: string;
  status: string;
  links: { video: string | null; live: string | null; repo: string | null };
  event: {
    id: string;
    name: string;
    mode: EventMode;
    role_level: RoleLevel;
    starts_at: string | null;
    ends_at: string | null;
  };
  criteria: { name: string; description: string; weight: number }[];
  talnex: ProjectTalnex & { confidence?: string | null };
  weighted_total: WeightedTotal | null;
  groups: CardGroup[];
  features: ReportFeature[];
  flags: ReportFlag[];
  checks: CardCheck[];
  run?: RunUsage | null;
  ai_opinion: AiOpinion | null;
  who_built_what?: WhoBuiltWhatRow[] | null;
  /** What the VM track did with the repository. Missing on older cards. */
  sandbox?: SandboxFacts | null;
  has_gaps: boolean;
  notes: string[];
}

export interface OverviewProject {
  id: string;
  team_name: string;
  status: string;
  has_video: boolean;
  has_live: boolean;
  has_repo: boolean;
  talnex_score10: number | null;
  coverage: number | null;
  weighted_total: number | null;
  groups: { group: string; score: number | null; coverage: number; low_coverage: boolean }[];
  /** How many flags of each level: info, review, strong. */
  flags: Partial<Record<FlagLevel, number>>;
  report_ready: boolean;
  /** The latest check: seconds from first job to last (so far while it runs), and its cost. Null if never checked. */
  run_seconds?: number | null;
  run_cost_usd?: number | null;
}

export interface EventOverview {
  event: EventSummary;
  projects: OverviewProject[];
}

/** One of up to three teams that built a feature best. Never one winner, never a ranking between features. */
export interface BestTeam {
  project_id: string;
  team_name: string;
  claim_id: string;
  claim_text: string;
  verdict: Verdict | null;
  confidence: Confidence | null;
  feature_score: number | null;
  reason: string | null;
  proof_urls: string[];
  label: string | null;
}

export interface CopyPair {
  team_a: { id: string; name: string };
  team_b: { id: string; name: string };
  shared_pct: number;
  level: FlagLevel | null;
  matching_files: unknown;
}

export interface EventCompare {
  ready: boolean;
  features: { name: string; best_teams: BestTeam[] }[];
  group_bests: { name: string; best_teams: BestTeam[] }[];
  copy_pairs: CopyPair[];
  notes: string[];
}

// ---------- Authorship proof ----------
// ai/talnex_ai/checks/authorship/report.py. Code is "written by GitHub account X", never by a person;
// "could not trace" never counts against anyone.

export interface AuthorshipFile {
  path: string;
  start: number;
  end: number;
  /** GitHub, at the exact lines of the traced commit. */
  url: string;
}

export interface AuthorshipAccount {
  /** A GitHub login, or "unlinked" for commits whose email is tied to no account. */
  account: string;
  line_share: number;
  lines: number;
  commits: number;
  days_spanned: number;
  first_pushed_at: string | null;
  last_pushed_at: string | null;
  date_source: "push" | "commit";
}

export interface Authorship {
  status: "traced" | "not_traced";
  reason: string | null;
  repo: string | null;
  commit_sha: string | null;
  files: AuthorshipFile[];
  accounts: AuthorshipAccount[];
  summary: string | null;
  /** Recruiter only: the share written by the candidate's own account; 0 means none of it. */
  candidate_share: number | null;
}

/** Hackathon card: each account against the features it wrote most of. No percentages, no ranking. */
export interface WhoBuiltWhatRow {
  account: string;
  features: string[];
}

// ---------- "Ask about this feature" (voice walkthrough) ----------
// Answered by ai/talnex_ai/reports/walkthrough; the API swaps screenshot keys for view_url.

export type WalkthroughSubject = "project" | "candidate_project";
export type WalkthroughStatus = "queued" | "answering" | "done" | "failed";

export type ProofRef =
  | { kind: "code"; path: string; start: number; end: number; commit_sha: string | null; url: string; snippet?: string }
  | { kind: "screenshot"; view_url?: string | null }
  | { kind: "step"; step_id: string }
  | { kind: "review"; note: string }
  | { kind: "authorship"; claim_id: string };

export interface WalkthroughSentence {
  text: string;
  proof: ProofRef[];
}

export interface WalkthroughMissing {
  item: string;
  status: "not_found_in_code" | "code_not_readable";
  proof: ProofRef[];
}

export interface WalkthroughAnswer {
  claim_id: string | null;
  claim_text: string | null;
  choices: { claim_id: string; text: string }[];
  flow: WalkthroughSentence[];
  seen: WalkthroughSentence[];
  missing: WalkthroughMissing[];
  not_found: boolean;
  spoken: string;
  label: string;
}

export interface Walkthrough {
  id: string;
  status: WalkthroughStatus;
  question: string | null;
  answer: WalkthroughAnswer | null;
  error: string | null;
  created_at: string;
  answered_at: string | null;
}

/** Resume claims against the repository history. Evidence only, never scored. */
export interface ClaimsVsGithub {
  claimed: { start?: string; end?: string; team?: string; team_size?: number; role?: string };
  actual: {
    repo: string;
    commit_count: number;
    first_commit: string | null;
    last_commit: string | null;
    contributors: { login: string; commits: number }[];
  } | null;
  insights: { signal: string; evidence: { tone: string; summary: string } }[];
  reason?: string;
}
