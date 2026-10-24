import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

const { apiFetch, revalidatePath } = vi.hoisted(() => ({ apiFetch: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));
vi.mock("next/cache", () => ({ revalidatePath }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw Object.assign(new Error("NEXT_REDIRECT"), { to });
  },
}));

const { createEvent } = await import("@/app/new/hackathon/actions");
const { addProject } = await import("@/app/events/[eventId]/actions");

const form = (fields: Record<string, string>) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
};
const event = {
  name: "Campus Hack",
  mode: "open_theme",
  role_level: "mid",
  starts_on: "2026-11-04",
  ends_on: "2026-11-05",
};

beforeEach(() => {
  apiFetch.mockReset();
  revalidatePath.mockReset();
});

describe("creating an event", () => {
  it("saves it and opens the event", async () => {
    apiFetch.mockResolvedValueOnce({ id: "e1" });
    const to = await createEvent({}, form(event)).catch((e) => e.to);
    expect(to).toBe("/events/e1");
    expect(apiFetch).toHaveBeenCalledWith("/v1/events", {
      method: "POST",
      body: expect.objectContaining({ name: "Campus Hack", mode: "open_theme", criteria: [] }),
    });
  });

  it("sends nothing when the form is wrong", async () => {
    expect(await createEvent({}, form({ ...event, ends_on: "2026-11-01" }))).toEqual({
      error: "The end date must be on or after the start date.",
    });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows the API's reason, or plain words when it breaks", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("name is required", 400));
    expect(await createEvent({}, form(event))).toEqual({ error: "name is required" });
    apiFetch.mockRejectedValueOnce(new ApiError("boom", 500));
    expect(await createEvent({}, form(event))).toEqual({ error: "We could not save the event. Please try again." });
  });
});

describe("adding a project", () => {
  const project = { team_name: "Team Rocket", repo_url: "https://github.com/rocket/app" };

  it("adds it to the event, refreshes the event page and says which team was added", async () => {
    apiFetch.mockResolvedValueOnce({ id: "p1" });
    expect(await addProject("e 1", {}, form(project))).toEqual({ added: "Team Rocket" });
    expect(apiFetch).toHaveBeenCalledWith("/v1/events/e%201/projects", {
      method: "POST",
      body: expect.objectContaining({ team_name: "Team Rocket", repo_url: "https://github.com/rocket/app" }),
    });
    expect(revalidatePath).toHaveBeenCalledWith("/events/e 1");
  });

  it("sends nothing without a link", async () => {
    expect(await addProject("e1", {}, form({ team_name: "Team Rocket" }))).toEqual({
      error: expect.stringMatching(/at least one link/),
    });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows the API's reason when it refuses", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("event not found", 404));
    expect(await addProject("e1", {}, form(project))).toEqual({ error: "event not found" });
  });
});
