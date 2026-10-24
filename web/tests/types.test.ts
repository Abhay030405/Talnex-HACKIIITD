import { describe, expect, it } from "vitest";

import { ROLES, eventState, homePath, isRole, modeLabel, roleLabel } from "@/lib/types";

describe("roles", () => {
  it("knows the two roles the API accepts and where each one lives", () => {
    expect(ROLES).toEqual(["recruiter", "organizer"]);
    expect(isRole("recruiter")).toBe(true);
    expect(isRole("organizer")).toBe(true);
    for (const other of ["admin", "", "Recruiter", undefined, null, 1]) expect(isRole(other)).toBe(false);
    expect(homePath("recruiter")).toBe("/recruiter");
    expect(homePath("organizer")).toBe("/organizer");
  });
});

describe("labels", () => {
  it("names role levels and event modes in words", () => {
    expect(roleLabel("fresher")).toBe("Fresher");
    expect(roleLabel("senior")).toBe("Senior");
    expect(modeLabel("open_theme")).toBe("Open theme");
    expect(modeLabel("fixed_problem")).toBe("Fixed problem");
  });
});

describe("event state", () => {
  const event = { starts_at: "2026-11-01T00:00:00Z", ends_at: "2026-11-02T23:59:59Z" };

  it("is upcoming, live or ended by the dates, with both edges counted as live", () => {
    expect(eventState(event, new Date("2026-10-31T23:59:59Z"))).toBe("upcoming");
    expect(eventState(event, new Date("2026-11-01T00:00:00Z"))).toBe("live");
    expect(eventState(event, new Date("2026-11-02T23:59:59Z"))).toBe("live");
    expect(eventState(event, new Date("2026-11-03T00:00:00Z"))).toBe("ended");
  });
});
