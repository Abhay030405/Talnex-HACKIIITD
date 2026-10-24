// The API client: exact request bodies, and every kind of failure turned into plain words.
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ApiError, errorMessage } from "../src/api.js";
import { toolError } from "../src/server.js";
import { estimate, roleProblem } from "../src/tools.js";
import { FakeApi } from "./fake-api.js";
import { apiFor, CAND, EVENT, PROJECT, ROLE, run, WALK } from "./helpers.js";

let fake: FakeApi;
beforeEach(async () => {
  fake = await new FakeApi().start();
});
afterEach(async () => fake.stop());

describe("request bodies match the Go API", () => {
  it("create_event fills the defaults and keeps the criteria", async () => {
    fake.json("POST", "/v1/events", 201, { id: EVENT });
    await run("create_event", apiFor(fake.url), { name: "Hack", mode: "fixed_problem", starts_at: "2026-10-23T00:00:00Z",
                                                  ends_at: "2026-10-24T00:00:00Z", criteria: [{ name: "Core", weight: 3 }] });
    expect(JSON.parse(fake.seen[0].body)).toEqual({ name: "Hack", mode: "fixed_problem", starts_at: "2026-10-23T00:00:00Z",
      ends_at: "2026-10-24T00:00:00Z", role_level: "fresher", sponsor_tools: [], criteria: [{ name: "Core", description: "", weight: 3 }] });
    expect(fake.seen[0].contentType).toBe("application/json");
  });

  it("add_project sends every link field", async () => {
    fake.json("POST", `/v1/events/${EVENT}/projects`, 201, { id: PROJECT });
    await run("add_project", apiFor(fake.url), { event_id: EVENT, team_name: "Ants", live_url: "https://ants.test", team_github_handles: ["ant"] });
    expect(JSON.parse(fake.seen[0].body)).toEqual({ team_name: "Ants", live_url: "https://ants.test", repo_url: "", video_url: "", team_github_handles: ["ant"] });
  });

  it("list_events keeps only the useful fields", async () => {
    fake.json("GET", "/v1/events", 200, [{ id: EVENT, name: "Hack", mode: "open_theme", role_level: "fresher", starts_at: "a", ends_at: "b", criteria: [1] }]);
    expect(await run("list_events", apiFor(fake.url))).toEqual([{ id: EVENT, name: "Hack", mode: "open_theme", role_level: "fresher", starts_at: "a", ends_at: "b" }]);
  });

  it("create_candidate posts the candidate, then the PDF as a form; role_id only when given", async () => {
    const pdf = join(await mkdtemp(join(tmpdir(), "talnex-mcp-")), "resume.pdf");
    await writeFile(pdf, "%PDF-1.4 test");
    fake.json("POST", "/v1/candidates", 201, { id: CAND }).json("POST", `/v1/candidates/${CAND}/resume`, 202, { candidate_id: CAND, run: 1 })
      .json("GET", `/v1/roles/${ROLE}`, 200, { auto_confirm: false });
    const api = apiFor(fake.url, "recruiter");
    await run("create_candidate", api, { resume_path: pdf, label: "Candidate 12", coding_handles: { codeforces: "cf" } });
    expect(JSON.parse(fake.seen[0].body)).toEqual({ label: "Candidate 12", role_level: "fresher", coding_handles: { codeforces: "cf" } });
    expect(fake.seen[1].contentType).toMatch(/^multipart\/form-data/);
    expect(fake.seen[1].body).toContain('name="resume"; filename="resume.pdf"');
    expect(fake.seen[1].body).toContain("%PDF-1.4 test");
    await run("create_candidate", api, { resume_path: pdf, role_id: ROLE });
    expect(JSON.parse(fake.seen[3].body)).toMatchObject({ role_id: ROLE });
  });

  it("create_candidate refuses a file that is not a PDF before calling anything", async () => {
    await expect(run("create_candidate", apiFor(fake.url, "recruiter"), { resume_path: "C:/cv.docx" })).rejects.toThrow("must be a PDF");
    expect(fake.seen).toHaveLength(0);
  });

  it("ask_project asks about a resume project at its own route, and says when the answer is still coming", async () => {
    fake.json("POST", `/v1/candidate-projects/${PROJECT}/walkthroughs`, 202, { id: WALK, status: "queued" })
      .json("GET", `/v1/walkthroughs/${WALK}`, 200, { id: WALK, status: "queued", answer: null, error: null });
    const out = await run("ask_project", apiFor(fake.url, "recruiter"),
                          { kind: "candidate_project", project_id: PROJECT, question: "How is search built?", wait_seconds: 0 });
    expect(out).toMatchObject({ status: "queued", note: expect.stringContaining(WALK) });
    expect(JSON.parse(fake.seen[0].body)).toEqual({ question: "How is search built?" });
  });

  it("who_am_i adds the configured role", async () => {
    fake.json("GET", "/v1/me", 200, { email: "organizer@talnex.test" });
    expect(await run("who_am_i", apiFor(fake.url))).toEqual({ email: "organizer@talnex.test", role: "organizer" });
  });
});

describe("failures in plain words", () => {
  it.each([
    [401, null, "Check AUTH_SECRET and TALNEX_EMAIL"],
    [403, null, "check TALNEX_ROLE"],
    [404, null, "Not found (or it belongs to another account)"],
    [502, null, "had a problem (error 502)"],
    [422, null, "refused (error 422)"],
    [400, { error: "ends_at is before starts_at" }, "ends_at is before starts_at"],
    [401, { error: "sign in required" }, "sign in required. The TalNex API did not accept the sign-in. Check AUTH_SECRET"],
  ])("status %i", (status, body, words) => {
    expect(errorMessage(body, status)).toContain(words);
  });

  it("an API that is not running", async () => {
    const url = fake.url;
    await fake.stop();
    await expect(run("list_events", apiFor(url))).rejects.toEqual(new ApiError(`Cannot reach the TalNex API at ${url}.`, 503));
  });

  it("an answer that is not JSON", async () => {
    fake.on("GET", "/v1/events", (_req, res) => res.end("<html>proxy page</html>"));
    await expect(run("list_events", apiFor(fake.url))).rejects.toThrow("could not be read");
  });

  it("an empty answer is null, not a failure", async () => {
    fake.on("DELETE", `/v1/candidates/${CAND}`, (_req, res) => {
      res.writeHead(204);
      res.end();
    });
    expect(await run("delete_candidate", apiFor(fake.url, "recruiter"), { candidate_id: CAND, confirm: true })).toEqual({ deleted: true });
  });

  it("a surprise inside the server never leaks its details", () => {
    const out = toolError(new TypeError("Cannot read properties of undefined (reading 'x')\n    at run (tools.ts:12:3)"));
    expect(out).toEqual({ isError: true, content: [{ type: "text", text: "Something went wrong in the TalNex MCP server." }] });
  });
});

describe("small pieces", () => {
  it("the estimate scales with the number of projects", () => {
    expect(estimate(4)).toMatchObject({ projects: 4, cost_usd: "about $0.40–$0.60" });
  });

  it("role checks", () => {
    expect(roleProblem({ name: "x", role: "any" }, "recruiter")).toBeNull();
    expect(roleProblem({ name: "x", role: "organizer" }, "organizer")).toBeNull();
    expect(roleProblem({ name: "list_events", role: "organizer" }, "recruiter")).toMatch(/TALNEX_ROLE=organizer/);
  });
});
