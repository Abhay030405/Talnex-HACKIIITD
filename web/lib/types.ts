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
