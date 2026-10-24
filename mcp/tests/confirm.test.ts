// Anything that spends money or cannot be undone starts only with confirm: true, and then exactly once.
// (confirm: true is only ever sent to the fake API here.)
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FakeApi } from "./fake-api.js";
import { apiFor, CAND, connect, EVENT, PROJECT, ROLE } from "./helpers.js";

let fake: FakeApi;
beforeEach(async () => {
  fake = await new FakeApi().start();
  fake.json("GET", `/v1/events/${EVENT}/overview`, 200, { projects: [{ team_name: "Ants", status: "submitted" }, { team_name: "Bees", status: "done" }] })
    .json("POST", `/v1/events/${EVENT}/run`, 202, { started: [PROJECT], skipped: [] })
    .json("GET", `/v1/projects/${PROJECT}`, 200, { team_name: "Ants", live_url: "https://a.test", repo_url: "", video_url: "", status: "done" })
    .json("POST", `/v1/projects/${PROJECT}/run`, 202, { project_id: PROJECT, run: 2 })
    .json("GET", `/v1/candidates/${CAND}/found`, 200, {
      projects: [{ name: "TinyTools", live_url: "https://t.test", repo_url: "", video_url: "", bullets: ["x"] }], coding_handles: { codeforces: "cf" } })
    .json("POST", `/v1/candidates/${CAND}/confirm`, 202, { ok: true })
    .json("DELETE", `/v1/candidates/${CAND}`, 204, null)
    .json("GET", `/v1/roles/${ROLE}`, 200, { title: "Backend intern", auto_confirm: true });
});
afterEach(async () => fake.stop());

const changes = () => fake.seen.filter((s) => s.method !== "GET").map((s) => `${s.method} ${s.path}`);

describe.each([
  ["run_event", "organizer", { event_id: EVENT }, `POST /v1/events/${EVENT}/run`],
  ["run_project", "organizer", { project_id: PROJECT }, `POST /v1/projects/${PROJECT}/run`],
  ["confirm_candidate", "recruiter", { candidate_id: CAND }, `POST /v1/candidates/${CAND}/confirm`],
  ["delete_candidate", "recruiter", { candidate_id: CAND }, `DELETE /v1/candidates/${CAND}`],
] as const)("%s", (name, role, args, change) => {
  it.each([[undefined], [false]])("confirm %s: nothing starts", async (confirm) => {
    const mcp = await connect(apiFor(fake.url, role));
    const out = await mcp.call(name, { ...args, ...(confirm === undefined ? {} : { confirm }) });
    await mcp.close();
    expect(out.isError).toBe(false);
    expect(out.json).toMatchObject(name === "delete_candidate" ? { deleted: false } : { started: false, how_to_start: expect.stringContaining("confirm: true") });
    expect(changes()).toEqual([]);
  });

  it("confirm true: the API is called exactly once", async () => {
    const mcp = await connect(apiFor(fake.url, role));
    const out = await mcp.call(name, { ...args, confirm: true });
    await mcp.close();
    expect(out.isError, out.text).toBe(false);
    expect(out.json).toMatchObject(name === "delete_candidate" ? { deleted: true } : { started: true, api_answer: expect.anything() });
    expect(changes()).toEqual([change]);
  });
});

describe("the previews say what would happen and what it costs", () => {
  it("run_event lists only the teams not checked yet", async () => {
    const mcp = await connect(apiFor(fake.url));
    const out = await mcp.call("run_event", { event_id: EVENT });
    await mcp.close();
    expect(out.json).toMatchObject({ would_check: ["Ants"], already_checked: ["Bees"],
                                     estimate: { projects: 1, cost_usd: "about $0.10–$0.15" } });
  });

  it("run_project shows the team's links", async () => {
    const mcp = await connect(apiFor(fake.url));
    const out = await mcp.call("run_project", { project_id: PROJECT });
    await mcp.close();
    expect(out.json).toMatchObject({ would_check: { team: "Ants", live_url: "https://a.test" }, estimate: { projects: 1 } });
  });

  it("confirm_candidate sends exactly what was found, or what you pass instead", async () => {
    const mcp = await connect(apiFor(fake.url, "recruiter"));
    const preview = await mcp.call("confirm_candidate", { candidate_id: CAND });
    expect(preview.json).toMatchObject({ would_check: [{ name: "TinyTools" }], coding_profiles: { codeforces: "cf" }, estimate: { projects: 1 } });
    await mcp.call("confirm_candidate", { candidate_id: CAND, confirm: true });
    await mcp.call("confirm_candidate", { candidate_id: CAND, confirm: true, projects: [{ name: "Other", repo_url: "https://github.com/a/b" }],
                                          coding_profiles: {} });
    await mcp.close();
    const bodies = fake.seen.filter((s) => s.method === "POST").map((s) => JSON.parse(s.body));
    expect(bodies).toEqual([
      { projects: [{ name: "TinyTools", live_url: "https://t.test", repo_url: "", video_url: "" }], coding_profiles: { codeforces: "cf" } },
      { projects: [{ name: "Other", live_url: "", repo_url: "https://github.com/a/b", video_url: "" }], coding_profiles: {} },
    ]);
  });
});

describe("a candidate under a role that starts checks by itself", () => {
  it("needs confirm before anything is created", async () => {
    const mcp = await connect(apiFor(fake.url, "recruiter"));
    const out = await mcp.call("create_candidate", { resume_path: "C:/nowhere/resume.pdf", role_id: ROLE });
    await mcp.close();
    expect(out.json).toMatchObject({ started: false, reason: expect.stringContaining("Backend intern") });
    expect(changes()).toEqual([]);
  });

  it("a role without auto confirm goes straight on", async () => {
    fake.json("GET", `/v1/roles/${ROLE}`, 200, { title: "Manual", auto_confirm: false });
    const mcp = await connect(apiFor(fake.url, "recruiter"));
    const out = await mcp.call("create_candidate", { resume_path: "C:/nowhere/resume.pdf", role_id: ROLE });
    await mcp.close();
    expect(out.isError).toBe(true);
    expect(out.text).toContain("Cannot read the file C:/nowhere/resume.pdf");
    expect(changes()).toEqual([]);
  });
});
