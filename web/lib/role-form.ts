// Turns the new-role form into what the API takes (backend/internal/candidates/roles.go), with the same rules, so a
// mistake is explained before anything is sent. The resumes are uploaded one by one afterwards (lib/resume.ts rules).
import { parseCriteria, splitList, type NewCriterion, type Parsed } from "@/lib/event-form";
import { ROLE_CHECKS, ROLE_LEVELS, type RoleCheck, type RoleLevel } from "@/lib/types";

export const MAX_ROLE_TITLE = 120;
export const MAX_JOB_TEXT = 20000;
export const MAX_PERSON_TEXT = 2000;
export const MAX_SKILLS = 30;
export const MAX_RESUMES = 50;

export interface NewRoleBody {
  title: string;
  job_description: string;
  person_wanted: string;
  skills: string[];
  role_level: RoleLevel;
  criteria: NewCriterion[];
  checks: Record<RoleCheck, boolean>;
  auto_confirm: boolean;
}

const text = (form: FormData, name: string) => String(form.get(name) ?? "").trim();

export function parseRoleForm(form: FormData): Parsed<NewRoleBody> {
  const title = text(form, "title").replace(/\s+/g, " ");
  if (!title) return { ok: false, error: "Give the role a title." };
  if (title.length > MAX_ROLE_TITLE) return { ok: false, error: "The role title is too long." };
  const jobDescription = text(form, "job_description");
  if (jobDescription.length > MAX_JOB_TEXT)
    return { ok: false, error: `The job description is longer than ${MAX_JOB_TEXT} characters.` };
  const personWanted = text(form, "person_wanted");
  if (personWanted.length > MAX_PERSON_TEXT)
    return { ok: false, error: `The description of the person is longer than ${MAX_PERSON_TEXT} characters.` };
  const skills = splitList(text(form, "skills"));
  if (skills.length > MAX_SKILLS) return { ok: false, error: `Use at most ${MAX_SKILLS} skills.` };
  const roleLevel = text(form, "role_level") as RoleLevel;
  if (!ROLE_LEVELS.some((r) => r.value === roleLevel)) return { ok: false, error: "Please pick a role level." };
  const criteria = parseCriteria(form);
  if (!criteria.ok) return criteria;
  const chosen = new Set(form.getAll("checks").map(String));
  const checks = Object.fromEntries(ROLE_CHECKS.map((c) => [c.value, chosen.has(c.value)])) as Record<RoleCheck, boolean>;
  if (!Object.values(checks).some(Boolean)) return { ok: false, error: "Choose at least one check to run." };
  return {
    ok: true,
    value: {
      title,
      job_description: jobDescription,
      person_wanted: personWanted,
      skills,
      role_level: roleLevel,
      criteria: criteria.value,
      checks,
      auto_confirm: form.get("auto_confirm") === "on",
    },
  };
}
