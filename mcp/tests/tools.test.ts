// Every tool, four ways, through a real MCP client: the happy path, bad input, an API error, and the wrong account.
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import type { Role } from "../src/settings.js";
import { TOOLS } from "../src/tools.js";
import { FakeApi } from "./fake-api.js";
import { apiFor, CAND, connect, EVENT, PROJECT, WALK } from "./helpers.js";

let pdf = "";
beforeAll(async () => {
  pdf = join(await mkdtemp(join(tmpdir(), "talnex-mcp-")), "resume.pdf");
  await writeFile(pdf, "%PDF-1.4 test");
});

interface Case {
  role: Role | "any";
  args: () => Record<string, unknown>;
  /** The routes the fake answers for the happy path. */
  routes: [method: string, path: string, status: number, value: unknown][];
  /** The requests the happy path makes, in order. */
  calls: string[];
  /** Bad input and a word the refusal must name; null when the tool takes no input. */
  bad: { args: Record<string, unknown>; names: string } | null;
  /** Arguments that reach the API, for the error case (defaults to args). */
  errorArgs?: () => Record<string, unknown>;
}

const SSE_ONE = 'event: replay.start\ndata: {}\n\nevent: stage.started\ndata: {"kind":"stage.started","subject":{"kind":"project","id":"p1"},"stage":"live_test","data":{}}\n\nevent: replay.done\ndata: {}\n\n';

const CASES: Record<string, Case> = {
  who_am_i: { role: "any", args: () => ({}), routes: [["GET", "/v1/me", 200, { email: "x@talnex.test" }]],
              calls: ["GET /v1/me"], bad: null },
  list_events: { role: "organizer", args: () => ({}), routes: [["GET", "/v1/events", 200, [{ id: EVENT, name: "Hack", mode: "open_theme", criteria: [] }]]],
                 calls: ["GET /v1/events"], bad: null },
  get_event: { role: "organizer", args: () => ({ event_id: EVENT }), routes: [["GET", `/v1/events/${EVENT}/overview`, 200, { projects: [] }]],
               calls: [`GET /v1/events/${EVENT}/overview`], bad: { args: { event_id: "not-an-id" }, names: "event_id" } },
  create_event: { role: "organizer", args: () => ({ name: "Hack", mode: "open_theme", starts_at: "2026-10-23T00:00:00Z", ends_at: "2026-10-24T00:00:00Z" }),
                  routes: [["POST", "/v1/events", 201, { id: EVENT }]], calls: ["POST /v1/events"],
                  bad: { args: { name: "Hack", mode: "weekly", starts_at: "a", ends_at: "b" }, names: "mode" } },
  add_project: { role: "organizer", args: () => ({ event_id: EVENT, team_name: "Ants", live_url: "https://ants.test" }),
                 routes: [["POST", `/v1/events/${EVENT}/projects`, 201, { id: PROJECT }]], calls: [`POST /v1/events/${EVENT}/projects`],
                 bad: { args: { event_id: EVENT, team_name: "Ants", live_url: "not a link" }, names: "live_url" } },
  run_event: { role: "organizer", args: () => ({ event_id: EVENT }), routes: [["GET", `/v1/events/${EVENT}/overview`, 200, { projects: [] }]],
               calls: [`GET /v1/events/${EVENT}/overview`], bad: { args: { event_id: 42 }, names: "event_id" } },
  run_project: { role: "organizer", args: () => ({ project_id: PROJECT }), routes: [["GET", `/v1/projects/${PROJECT}`, 200, { team_name: "Ants" }]],
                 calls: [`GET /v1/projects/${PROJECT}`], bad: { args: { project_id: PROJECT, confirm: "yes" }, names: "confirm" } },
  get_proof_card: { role: "organizer", args: () => ({ project_id: PROJECT }), routes: [["GET", `/v1/projects/${PROJECT}/proof`, 200, { team_name: "Ants" }]],
                    calls: [`GET /v1/projects/${PROJECT}/proof`], bad: { args: {}, names: "project_id" } },
  compare_event: { role: "organizer", args: () => ({ event_id: EVENT }), routes: [["GET", `/v1/events/${EVENT}/compare`, 200, { ready: true }]],
                   calls: [`GET /v1/events/${EVENT}/compare`], bad: { args: { event_id: "" }, names: "event_id" } },
  ask_project: { role: "any", args: () => ({ kind: "project", project_id: PROJECT, question: "How does login work?", wait_seconds: 5 }),
                 routes: [["POST", `/v1/projects/${PROJECT}/walkthroughs`, 202, { id: WALK, status: "queued" }],
                          ["GET", `/v1/walkthroughs/${WALK}`, 200, { id: WALK, status: "answered", answer: { text: "With a magic link" }, error: null }]],
                 calls: [`POST /v1/projects/${PROJECT}/walkthroughs`, `GET /v1/walkthroughs/${WALK}`],
                 bad: { args: { kind: "project", project_id: PROJECT, question: "hi" }, names: "question" } },
  list_roles: { role: "recruiter", args: () => ({}), routes: [["GET", "/v1/roles", 200, []]], calls: ["GET /v1/roles"], bad: null },
  list_candidates: { role: "recruiter", args: () => ({}), routes: [["GET", "/v1/candidates", 200, []]], calls: ["GET /v1/candidates"], bad: null },
  create_candidate: { role: "recruiter", args: () => ({ resume_path: pdf, label: "Candidate 12" }),
                      routes: [["POST", "/v1/candidates", 201, { id: CAND }], ["POST", `/v1/candidates/${CAND}/resume`, 202, { candidate_id: CAND, run: 1 }]],
                      calls: ["POST /v1/candidates", `POST /v1/candidates/${CAND}/resume`],
                      bad: { args: { resume_path: "x.pdf", role_level: "boss" }, names: "role_level" } },
  get_found_projects: { role: "recruiter", args: () => ({ candidate_id: CAND }), routes: [["GET", `/v1/candidates/${CAND}/found`, 200, { projects: [] }]],
                        calls: [`GET /v1/candidates/${CAND}/found`], bad: { args: { candidate_id: "12" }, names: "candidate_id" } },
  confirm_candidate: { role: "recruiter", args: () => ({ candidate_id: CAND }),
                       routes: [["GET", `/v1/candidates/${CAND}/found`, 200, { projects: [], coding_handles: {} }]],
                       calls: [`GET /v1/candidates/${CAND}/found`],
                       bad: { args: { candidate_id: CAND, projects: [{ live_url: "https://a.test" }] }, names: "name" } },
  get_progress: { role: "recruiter", args: () => ({ candidate_id: CAND }), routes: [["GET", `/v1/candidates/${CAND}/progress`, 200, { stages: [] }]],
                  calls: [`GET /v1/candidates/${CAND}/progress`], bad: { args: { candidate_id: null }, names: "candidate_id" } },
  get_report: { role: "recruiter", args: () => ({ candidate_id: CAND }), routes: [["GET", `/v1/candidates/${CAND}/report`, 200, { projects: [] }]],
                calls: [`GET /v1/candidates/${CAND}/report`], bad: { args: { candidate_id: "bad" }, names: "candidate_id" } },
  delete_candidate: { role: "recruiter", args: () => ({ candidate_id: CAND }), routes: [], calls: [],
                      bad: { args: { candidate_id: CAND, confirm: "true" }, names: "confirm" },
                      errorArgs: () => ({ candidate_id: CAND, confirm: true }) },
  watch_live: { role: "any", args: () => ({ kind: "project", id: PROJECT, seconds: 1 }), routes: [], calls: [`GET /v1/live/project/${PROJECT}`],
                bad: { args: { kind: "project", id: PROJECT, seconds: 500 }, names: "seconds" } },
};

let fake: FakeApi;
beforeEach(async () => {
  fake = await new FakeApi().start();
  fake.on("GET", `/v1/live/project/${PROJECT}`, (_req, res) => {
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    res.write(SSE_ONE);
  });
});
afterEach(async () => fake.stop());

const roleFor = (c: Case): Role => (c.role === "any" ? "organizer" : c.role);
const other = (r: Role): Role => (r === "organizer" ? "recruiter" : "organizer");
const noStack = (text: string) => expect(text).not.toMatch(/\n\s+at |\.ts:\d+|node:internal/);

it("the matrix covers every tool the server offers", async () => {
  const mcp = await connect(apiFor(fake.url));
  const offered = (await mcp.client.listTools()).tools.map((t) => t.name).sort();
  await mcp.close();
  expect(offered).toEqual(Object.keys(CASES).sort());
  expect(TOOLS.map((t) => t.name).sort()).toEqual(offered);
});

describe.each(Object.entries(CASES))("%s", (name, c) => {
  it("happy path: calls the right routes and answers JSON", async () => {
    for (const [method, path, status, value] of c.routes) fake.json(method, path, status, value);
    const mcp = await connect(apiFor(fake.url, roleFor(c)));
    const out = await mcp.call(name, c.args());
    await mcp.close();
    expect(out.isError, out.text).toBe(false);
    expect(out.json).not.toBeNull();
    expect(fake.seen.map((s) => `${s.method} ${s.path}`)).toEqual(c.calls);
    for (const s of fake.seen) expect(s.auth).toMatch(/^Bearer ey/);
  });

  it("bad input: refused with a clear message, nothing sent", async () => {
    const mcp = await connect(apiFor(fake.url, roleFor(c)));
    if (c.bad) {
      const out = await mcp.call(name, c.bad.args);
      expect(out.isError).toBe(true);
      expect(out.text).toMatch(/Input validation error|Invalid/i);
      expect(out.text).toContain(c.bad.names);
      expect(fake.seen).toHaveLength(0);
    } else {
      // no input to get wrong: extra arguments are ignored and the call still works
      for (const [method, path, status, value] of c.routes) fake.json(method, path, status, value);
      const out = await mcp.call(name, { surprise: true });
      expect(out.isError).toBe(false);
    }
    await mcp.close();
  });

  it.each([
    [500, { error: "the database is down" }, "the database is down"],
    [404, { error: "not found" }, "not found"],
    [503, {}, "had a problem (error 503)"],
  ])("API error %i: a tool error naming the cause, no stack trace", async (status, body, words) => {
    fake.failAll(status, body);
    const mcp = await connect(apiFor(fake.url, roleFor(c)));
    const out = await mcp.call(name, (c.errorArgs ?? c.args)());
    await mcp.close();
    expect(out.isError).toBe(true);
    expect(out.text).toContain(words);
    noStack(out.text);
  });

  it(c.role === "any" ? "either account may use it" : "the other account gets a clear refusal", async () => {
    for (const [method, path, status, value] of c.routes) fake.json(method, path, status, value);
    if (c.role === "any") {
      for (const role of ["organizer", "recruiter"] as Role[]) {
        const mcp = await connect(apiFor(fake.url, role));
        const out = await mcp.call(name, c.args());
        await mcp.close();
        expect(out.isError, out.text).toBe(false);
      }
      return;
    }
    const mcp = await connect(apiFor(fake.url, other(c.role)));
    const out = await mcp.call(name, c.args());
    await mcp.close();
    expect(out.isError).toBe(true);
    expect(out.text).toContain(`${name} is for ${c.role} accounts`);
    expect(out.text).toContain(`TALNEX_ROLE=${c.role}`);
    expect(fake.seen).toHaveLength(0);
  });
});
