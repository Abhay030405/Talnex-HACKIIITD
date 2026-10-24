import { describe, expect, it } from "vitest";

import { MAX_TEAM_HANDLES, parseEventForm, parseProjectForm, splitList } from "@/lib/event-form";

const form = (fields: Record<string, string | string[]>) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) for (const one of [v].flat()) f.append(k, one);
  return f;
};

const openTheme = {
  name: " Campus Hack ",
  mode: "open_theme",
  role_level: "fresher",
  starts_on: "2026-11-04",
  ends_on: "2026-11-06",
};
const fixed = (rows: { name: string; description?: string; weight: string }[]) =>
  form({
    ...openTheme,
    mode: "fixed_problem",
    criterion_name: rows.map((r) => r.name),
    criterion_description: rows.map((r) => r.description ?? ""),
    criterion_weight: rows.map((r) => r.weight),
  });

describe("splitList", () => {
  it("trims, drops empties and repeats", () => {
    expect(splitList(" Stripe, Twilio ,, stripe\nVercel ")).toEqual(["Stripe", "Twilio", "Vercel"]);
    expect(splitList("")).toEqual([]);
  });
});

describe("event form", () => {
  it("builds the API's shape for an open-theme event, covering whole days in UTC", () => {
    const parsed = parseEventForm(form({ ...openTheme, sponsor_tools: "Stripe, Twilio" }));
    expect(parsed).toEqual({
      ok: true,
      value: {
        name: "Campus Hack",
        mode: "open_theme",
        role_level: "fresher",
        starts_at: "2026-11-04T00:00:00Z",
        ends_at: "2026-11-06T23:59:59Z",
        sponsor_tools: ["Stripe", "Twilio"],
        criteria: [],
        brief: "",
        checks: {},
      },
    });
  });

  it("allows a one-day event", () => {
    expect(parseEventForm(form({ ...openTheme, ends_on: "2026-11-04" })).ok).toBe(true);
  });

  it("never sends criteria for an open-theme event, which the API refuses", () => {
    const parsed = parseEventForm(form({ ...openTheme, criterion_name: "Speed", criterion_weight: "2" }));
    expect(parsed.ok && parsed.value.criteria).toEqual([]);
  });

  it.each([
    [{ name: "" }, /name/],
    [{ mode: "other" }, /event type/],
    [{ role_level: "boss" }, /role level/],
    [{ starts_on: "" }, /dates/],
    [{ starts_on: "04/11/2026" }, /dates/],
    [{ ends_on: "2026-11-03" }, /on or after/],
  ])("explains %p", (change, words) => {
    const parsed = parseEventForm(form({ ...openTheme, ...change }));
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.error).toMatch(words);
  });

  it("takes the criteria of a fixed-problem event, skipping blank rows", () => {
    const parsed = parseEventForm(
      fixed([
        { name: "Core flow", description: "It works end to end", weight: "3" },
        { name: "", weight: "" },
        { name: "Polish", weight: "1.5" },
      ]),
    );
    expect(parsed.ok && parsed.value.criteria).toEqual([
      { name: "Core flow", description: "It works end to end", weight: 3 },
      { name: "Polish", description: "", weight: 1.5 },
    ]);
  });

  it.each([
    [[{ name: "", weight: "" }], /at least one scoring criterion/],
    [[{ name: "Speed", weight: "0" }], /weight above 0/],
    [[{ name: "Speed", weight: "fast" }], /weight above 0/],
    [[{ name: "", description: "no name", weight: "2" }], /needs a name/],
    [
      [
        { name: "Speed", weight: "1" },
        { name: "speed", weight: "2" },
      ],
      /appears twice/,
    ],
  ])("refuses fixed-problem criteria the API would refuse: %j", (rows, words) => {
    const parsed = parseEventForm(fixed(rows));
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.error).toMatch(words);
  });
});

describe("project form", () => {
  const team = { team_name: " Team Rocket ", live_url: "https://rocket.example" };

  it("builds the API's shape, with clean GitHub accounts", () => {
    const parsed = parseProjectForm(
      form({ ...team, team_github_handles: "@Alice, bob,alice , ", test_login_ref: " rocket-demo " }),
    );
    expect(parsed).toEqual({
      ok: true,
      value: {
        team_name: "Team Rocket",
        video_url: "",
        live_url: "https://rocket.example",
        repo_url: "",
        test_login_ref: "rocket-demo",
        team_github_handles: ["alice", "bob"],
        abstract: "",
      },
    });
  });

  it.each([
    [{ team_name: "" }, /team a name/],
    [{ live_url: "" }, /at least one link/],
    [{ live_url: "rocket.example" }, /Live site must be a full web address/],
    [{ repo_url: "ftp://x.example/repo" }, /Repository must be a full web address/],
    [{ team_github_handles: "alice, -bad-" }, /“-bad-” is not a GitHub account/],
    [{ team_github_handles: "a_b" }, /not a GitHub account/],
    [
      { team_github_handles: Array.from({ length: MAX_TEAM_HANDLES + 1 }, (_, i) => `user${i}`).join(",") },
      /at most 10/,
    ],
  ])("explains %p", (change, words) => {
    const parsed = parseProjectForm(form({ ...team, ...change }));
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.error).toMatch(words);
  });
});
