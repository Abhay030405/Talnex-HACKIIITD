import { describe, expect, it } from "vitest";

import { parseRoleForm } from "@/lib/role-form";

function form(values: Record<string, string | string[]>): FormData {
  const f = new FormData();
  for (const [key, value] of Object.entries(values)) for (const v of [value].flat()) f.append(key, v);
  return f;
}

const BASE = { title: " Backend   intern ", role_level: "junior", checks: ["live_test", "coding_profiles"] };

describe("new role form", () => {
  it("turns the form into what the API takes", () => {
    const parsed = parseRoleForm(
      form({
        ...BASE,
        job_description: "Build APIs in Go.",
        skills: "Go, PostgreSQL ,, go",
        criterion_name: ["Backend", "", "UI"],
        criterion_description: ["APIs work", "", ""],
        criterion_weight: ["3", "", "1"],
        auto_confirm: "on",
      }),
    );
    expect(parsed).toEqual({
      ok: true,
      value: {
        title: "Backend intern",
        job_description: "Build APIs in Go.",
        person_wanted: "",
        skills: ["Go", "PostgreSQL"],
        role_level: "junior",
        criteria: [
          { name: "Backend", description: "APIs work", weight: 3 },
          { name: "UI", description: "", weight: 1 },
        ],
        checks: { live_test: true, code_review: false, coding_profiles: true, linkedin: false },
        auto_confirm: true,
      },
    });
  });

  it("explains each mistake before anything is sent", () => {
    expect(parseRoleForm(form({ ...BASE, title: "" }))).toEqual({ ok: false, error: "Give the role a title." });
    expect(parseRoleForm(form({ ...BASE, role_level: "boss" }))).toEqual({ ok: false, error: "Please pick a role level." });
    expect(parseRoleForm(form({ ...BASE, checks: [] }))).toEqual({ ok: false, error: "Choose at least one check to run." });
    const noWeight = parseRoleForm(form({ ...BASE, criterion_name: "UI", criterion_weight: "0" }));
    expect(noWeight.ok).toBe(false);
  });

  it("leaves auto confirm off when the box is not ticked", () => {
    const parsed = parseRoleForm(form(BASE));
    expect(parsed.ok && parsed.value.auto_confirm).toBe(false);
  });
});
