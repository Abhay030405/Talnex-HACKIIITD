// End-to-end check of the built server against a running TalNex stack (docker compose up), the way an assistant uses
// it: spawn dist/index.js over stdio with the MCP SDK client and call the tools. It NEVER passes confirm: true, so no
// paid check starts. AUTH_SECRET is read from the repository's .env (never printed).
//   npm run e2e          (needs Node 22.6+ for --experimental-strip-types; the server itself needs Node 20+)
// Settings: TALNEX_API_URL (default http://localhost:8080), TALNEX_E2E_ORGANIZER, TALNEX_E2E_RECRUITER.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SERVER = resolve(HERE, "..", "dist", "index.js");
const RESUME = resolve(HERE, "..", "..", "testdata", "resumes", "test_resume.pdf");
const API_URL = process.env.TALNEX_API_URL ?? "http://localhost:8080";
const ORGANIZER = process.env.TALNEX_E2E_ORGANIZER ?? "edge-organizer@talnex.test";
const RECRUITER = process.env.TALNEX_E2E_RECRUITER ?? "edge-recruiter@talnex.test";
// A run that already finished on the local stack: the planted "honest" app, TinyTools.
const KNOWN_PROJECT = "b93b6f22-5c31-43db-bd4c-a41598568007";

/** AUTH_SECRET from the environment, or from the nearest .env above this folder. The value is never printed. */
function authSecret(): string {
  if (process.env.AUTH_SECRET) return process.env.AUTH_SECRET;
  for (let dir = HERE; ; dir = dirname(dir)) {
    const file = join(dir, ".env");
    if (existsSync(file)) {
      const line = readFileSync(file, "utf8").split(/\r?\n/).find((l) => l.startsWith("AUTH_SECRET="));
      const value = line?.slice("AUTH_SECRET=".length).trim().replace(/^["']|["']$/g, "");
      if (value) return value;
    }
    if (dirname(dir) === dir) throw new Error("AUTH_SECRET is not set and no .env with it was found above mcp/scripts");
  }
}

let failures = 0;
const results: string[] = [];
function check(ok: boolean, what: string, detail = ""): void {
  if (!ok) failures += 1;
  const line = `${ok ? "PASS" : "FAIL"}  ${what}${detail ? `  (${detail})` : ""}`;
  results.push(line);
  console.log(line);
}

interface Called {
  isError: boolean;
  text: string;
  json: any; // eslint-disable-line @typescript-eslint/no-explicit-any
}

async function session(email: string, role: "organizer" | "recruiter", secret: string) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [SERVER],
    env: { PATH: process.env.PATH ?? "", SYSTEMROOT: process.env.SYSTEMROOT ?? "",
           TALNEX_API_URL: API_URL, AUTH_SECRET: secret, TALNEX_EMAIL: email, TALNEX_ROLE: role },
    stderr: "ignore",
  });
  const client = new Client({ name: "talnex-e2e", version: "0" });
  await client.connect(transport);
  return {
    client,
    async call(name: string, args: Record<string, unknown> = {}): Promise<Called> {
      const r = await client.callTool({ name, arguments: args }, undefined, { timeout: 150_000 });
      const text = (r.content as { text: string }[]).map((c) => c.text).join("\n");
      let json = null;
      try {
        json = JSON.parse(text);
      } catch { /* plain words */ }
      return { isError: r.isError === true, text, json };
    },
    close: () => client.close(),
  };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function startup(secret: string): Promise<void> {
  console.log("\n== Startup");
  const missing = spawnSync(process.execPath, [SERVER], {
    env: { PATH: process.env.PATH ?? "", TALNEX_API_URL: API_URL, TALNEX_EMAIL: ORGANIZER, TALNEX_ROLE: "organizer" },
    encoding: "utf8", timeout: 10_000,
  });
  check(missing.status === 1 && missing.stderr.includes("AUTH_SECRET"), "a missing AUTH_SECRET stops startup and names it",
        missing.stderr.trim().split("\n")[0]);
  const wrong = await session(ORGANIZER, "organizer", `${secret}-wrong`);
  const refused = await wrong.call("list_events");
  await wrong.close();
  check(refused.isError && /AUTH_SECRET|sign-in|token/i.test(refused.text), "a wrong AUTH_SECRET is a clear tool error", refused.text);
}

async function organizer(secret: string): Promise<void> {
  console.log(`\n== Organizer (${ORGANIZER})`);
  const s = await session(ORGANIZER, "organizer", secret);
  const tools = (await s.client.listTools()).tools.map((t) => t.name);
  check(tools.length === 19, "the server lists its tools", `${tools.length} tools`);

  const me = await s.call("who_am_i");
  check(!me.isError && me.json?.email === ORGANIZER, "who_am_i", me.isError ? me.text : `${me.json.email} as ${me.json.role}`);

  const events = await s.call("list_events");
  check(!events.isError && Array.isArray(events.json), "list_events", `${events.json?.length ?? 0} events`);

  const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
  const created = await s.call("create_event", {
    name: `TalNex test: MCP e2e ${stamp}`, mode: "fixed_problem",
    starts_at: "2026-10-23T09:00:00Z", ends_at: "2026-10-24T18:00:00Z",
    criteria: [{ name: "Core tools work", description: "The converter, todos and timer work", weight: 3 },
               { name: "Ease of use", description: "A first-time user finds each tool", weight: 1 }],
  });
  const eventId = created.json?.id as string | undefined;
  check(!created.isError && !!eventId, "create_event (fixed problem, 2 criteria)", created.isError ? created.text : `event ${eventId}`);
  if (!eventId) return void (await s.close());

  const added = await s.call("add_project", { event_id: eventId, team_name: "TinyTools", live_url: "https://talnex-honest.vercel.app" });
  const projectId = added.json?.id as string | undefined;
  check(!added.isError && !!projectId, "add_project (TinyTools)", added.isError ? added.text : `project ${projectId}`);

  const event = await s.call("get_event", { event_id: eventId });
  const teams = (event.json?.projects ?? []) as { team_name: string; status: string }[];
  check(!event.isError && teams.some((t) => t.team_name === "TinyTools"), "get_event lists the team",
        teams.map((t) => `${t.team_name}: ${t.status}`).join(", "));

  if (projectId) {
    const preview = await s.call("run_project", { project_id: projectId });
    check(!preview.isError && preview.json?.started === false, "run_project WITHOUT confirm only previews",
          `would check ${preview.json?.would_check?.live_url}, ${preview.json?.estimate?.cost_usd}`);
  }
  const eventPreview = await s.call("run_event", { event_id: eventId });
  check(!eventPreview.isError && eventPreview.json?.started === false, "run_event WITHOUT confirm only previews",
        `would check ${JSON.stringify(eventPreview.json?.would_check)}, ${eventPreview.json?.estimate?.cost_usd}`);
  const after = await s.call("get_event", { event_id: eventId });
  const still = (after.json?.projects ?? []) as { status: string }[];
  check(still.every((t) => t.status === "submitted"), "nothing started: the team is still 'submitted'", still.map((t) => t.status).join(","));

  const wrongRole = await s.call("list_candidates");
  check(wrongRole.isError && wrongRole.text.includes("for recruiter accounts"), "a recruiter tool is refused for an organizer");

  console.log(`\n== Existing results (project ${KNOWN_PROJECT})`);
  const card = await s.call("get_proof_card", { project_id: KNOWN_PROJECT });
  const claims = (card.json?.features ?? []) as { verdict?: string | null }[];
  const verdicts = claims.reduce<Record<string, number>>((m, c) => ({ ...m, [c.verdict ?? "none"]: (m[c.verdict ?? "none"] ?? 0) + 1 }), {});
  check(!card.isError && claims.length > 0, "get_proof_card",
        card.isError ? card.text : `${card.json.team_name}: ${claims.length} claims ${JSON.stringify(verdicts)}, ` +
        `TalNex score ${card.json.talnex?.score10 ?? "none"}/10, coverage ${card.json.talnex?.coverage}, ${card.json.flags?.length ?? 0} flags`);

  const t0 = Date.now();
  const live = await s.call("watch_live", { kind: "project", id: KNOWN_PROJECT, seconds: 10 });
  const took = Math.round((Date.now() - t0) / 1000);
  const subject = live.json?.subjects?.[0];
  const statuses = subject ? Object.values(subject.claims as Record<string, { status: string }>).map((c) => c.status) : [];
  check(!live.isError && live.json?.events > 0 && took >= 9 && took <= 20, "watch_live replays the run for about 10 s",
        live.isError ? live.text : `${took}s, ${live.json.events} events, ${statuses.length} claims [${statuses.join(",")}], ` +
        `${subject.actions} actions, browser $${subject.browser_cost_usd}, reconnects ${live.json.reconnects}`);
  await s.close();
}

async function recruiter(secret: string): Promise<void> {
  console.log(`\n== Recruiter (${RECRUITER})`);
  const s = await session(RECRUITER, "recruiter", secret);
  const created = await s.call("create_candidate", { resume_path: RESUME, label: "TalNex test: MCP e2e" });
  const candidateId = created.json?.candidate?.id as string | undefined;
  check(!created.isError && !!candidateId, "create_candidate with the test resume (no role)",
        created.isError ? created.text : `candidate ${candidateId}`);
  if (!candidateId) return void (await s.close());

  let found: Called | null = null;
  for (let i = 0; i < 30; i++) {
    found = await s.call("get_found_projects", { candidate_id: candidateId });
    if (!found.isError && (found.json?.projects?.length ?? 0) > 0) break;
    await sleep(4000);
  }
  const projects = (found?.json?.projects ?? []) as { name: string }[];
  check(!!found && !found.isError && projects.length > 0, "get_found_projects (after the resume is read)",
        found?.isError ? found.text : projects.map((p) => p.name).join(", "));

  const progress = await s.call("get_progress", { candidate_id: candidateId });
  check(!progress.isError, "get_progress", progress.isError ? progress.text : progress.text.replace(/\s+/g, " ").slice(0, 160));

  const preview = await s.call("confirm_candidate", { candidate_id: candidateId });
  check(!preview.isError && preview.json?.started === false, "confirm_candidate WITHOUT confirm only previews",
        `${preview.json?.would_check?.length ?? 0} projects, ${preview.json?.estimate?.cost_usd}`);

  const wrongRole = await s.call("list_events");
  check(wrongRole.isError && wrongRole.text.includes("for organizer accounts"), "an organizer tool is refused for a recruiter");
  await s.close();
}

async function main(): Promise<void> {
  if (!existsSync(SERVER)) throw new Error("dist/index.js is missing: run npm run build first");
  const secret = authSecret();
  console.log(`TalNex MCP e2e against ${API_URL} (no confirm: true anywhere, nothing paid starts)`);
  await startup(secret);
  await organizer(secret);
  await recruiter(secret);
  console.log(`\n${results.length - failures} passed, ${failures} failed`);
  process.exit(failures ? 1 : 0);
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : String(e));
  process.exit(1);
});
