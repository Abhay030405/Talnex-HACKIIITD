// Turns the hackathon and project forms into what the API takes, with the same rules it checks
// (backend/internal/events and backend/internal/projects), so a mistake is explained before anything is sent.
import { ROLE_LEVELS, type EventMode, type RoleLevel } from "@/lib/types";

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

const fail = <T>(error: string): Parsed<T> => ({ ok: false, error });
const text = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
const texts = (form: FormData, name: string) => form.getAll(name).map((v) => String(v).trim());

/** "Stripe, Twilio ,, stripe" → ["Stripe", "Twilio"]: trimmed, empty ones dropped, repeats (any case) dropped. */
export function splitList(value: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of value.split(/[,\n]/).map((s) => s.trim())) {
    if (!item || seen.has(item.toLowerCase())) continue;
    seen.add(item.toLowerCase());
    out.push(item);
  }
  return out;
}

// ---------- Event ----------

export interface NewCriterion {
  name: string;
  description: string;
  weight: number;
}

export interface NewEventBody {
  name: string;
  mode: EventMode;
  role_level: RoleLevel;
  starts_at: string;
  ends_at: string;
  sponsor_tools: string[];
  criteria: NewCriterion[];
}

export const MAX_CRITERIA = 12;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Rows of the criteria editor; rows left fully empty are ignored. */
export function parseCriteria(form: FormData): Parsed<NewCriterion[]> {
  const names = texts(form, "criterion_name");
  const descriptions = texts(form, "criterion_description");
  const weights = texts(form, "criterion_weight");
  const criteria: NewCriterion[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < names.length; i++) {
    const name = names[i];
    const description = descriptions[i] ?? "";
    const weightText = weights[i] ?? "";
    if (!name && !description && !weightText) continue;
    const row = criteria.length + 1;
    if (!name) return fail(`Criterion ${row} needs a name.`);
    if (seen.has(name.toLowerCase())) return fail(`The criterion “${name}” appears twice.`);
    seen.add(name.toLowerCase());
    const weight = Number(weightText);
    if (!Number.isFinite(weight) || weight <= 0) return fail(`Give “${name}” a weight above 0.`);
    criteria.push({ name, description, weight });
  }
  if (criteria.length > MAX_CRITERIA) return fail(`Use at most ${MAX_CRITERIA} criteria.`);
  return { ok: true, value: criteria };
}

export function parseEventForm(form: FormData): Parsed<NewEventBody> {
  const name = text(form, "name");
  if (!name) return fail("Please give the event a name.");

  const mode = text(form, "mode");
  if (mode !== "open_theme" && mode !== "fixed_problem") return fail("Please pick the event type.");

  const roleLevel = text(form, "role_level");
  if (!ROLE_LEVELS.some((r) => r.value === roleLevel)) return fail("Please pick a role level.");

  const start = text(form, "starts_on");
  const end = text(form, "ends_on");
  if (!DAY.test(start) || !DAY.test(end)) return fail("Please choose the start and end dates.");
  if (end < start) return fail("The end date must be on or after the start date.");

  let criteria: NewCriterion[] = [];
  if (mode === "fixed_problem") {
    const parsed = parseCriteria(form);
    if (!parsed.ok) return parsed;
    if (parsed.value.length === 0) return fail("A fixed-problem event needs at least one scoring criterion.");
    criteria = parsed.value;
  }

  return {
    ok: true,
    value: {
      name,
      mode,
      role_level: roleLevel as RoleLevel,
      // The event runs from the start of its first day to the end of its last day, in UTC like the API.
      starts_at: `${start}T00:00:00Z`,
      ends_at: `${end}T23:59:59Z`,
      sponsor_tools: splitList(text(form, "sponsor_tools")),
      criteria,
    },
  };
}

// ---------- Project ----------

export interface NewProjectBody {
  team_name: string;
  video_url: string;
  live_url: string;
  repo_url: string;
  test_login_ref: string;
  team_github_handles: string[];
}

export const MAX_TEAM_HANDLES = 10;
// GitHub's rule for account names: letters, digits and single hyphens, not at the start or end, at most 39.
const GITHUB_LOGIN = /^[a-z0-9](?:[a-z0-9]|-[a-z0-9]){0,38}$/;

function webAddress(value: string): boolean {
  try {
    const u = new URL(value);
    return (u.protocol === "http:" || u.protocol === "https:") && Boolean(u.hostname);
  } catch {
    return false;
  }
}

export function parseProjectForm(form: FormData): Parsed<NewProjectBody> {
  const team = text(form, "team_name");
  if (!team) return fail("Please give the team a name.");

  const links = { video_url: "Demo video", live_url: "Live site", repo_url: "Repository" } as const;
  const values = { video_url: "", live_url: "", repo_url: "" };
  for (const [field, label] of Object.entries(links) as [keyof typeof links, string][]) {
    const value = text(form, field);
    if (value && !webAddress(value)) return fail(`${label} must be a full web address starting with https://.`);
    values[field] = value;
  }
  if (!values.video_url && !values.live_url && !values.repo_url) {
    return fail("Give at least one link: the demo video, the live site or the repository.");
  }

  const handles = [
    ...new Set(splitList(text(form, "team_github_handles")).map((h) => h.replace(/^@/, "").toLowerCase())),
  ];
  const bad = handles.find((h) => !GITHUB_LOGIN.test(h));
  if (bad) return fail(`“${bad}” is not a GitHub account name.`);
  if (handles.length > MAX_TEAM_HANDLES) return fail(`List at most ${MAX_TEAM_HANDLES} GitHub accounts.`);

  return {
    ok: true,
    value: { team_name: team, ...values, test_login_ref: text(form, "test_login_ref"), team_github_handles: handles },
  };
}
