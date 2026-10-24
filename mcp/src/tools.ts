// The TalNex tools an assistant can call. Every tool goes through the Go API as the configured person, so results
// stay private to their owner. Anything that spends money (starting checks) needs `confirm: true`; without it the
// tool only says what WOULD be checked and roughly what it costs.
import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import { z } from "zod";

import { ApiError, type TalnexApi } from "./api.js";
import { LIVE_KINDS, watchLive } from "./live.js";

/** From our measured runs: about $0.10–0.15 and 5 minutes per project of about 7 claims. An estimate, not a quote. */
export const ESTIMATE = { lowUsd: 0.1, highUsd: 0.15, minutesPerProject: 5 };

export function estimate(projects: number) {
  return {
    projects,
    cost_usd: `about $${(ESTIMATE.lowUsd * projects).toFixed(2)}–$${(ESTIMATE.highUsd * projects).toFixed(2)}`,
    time: `about ${ESTIMATE.minutesPerProject} minutes per project (projects run side by side)`,
    note: "An estimate from earlier runs; the real cost depends on how many claims each project has.",
  };
}

const LEVELS = ["fresher", "junior", "mid", "senior"] as const;
const id = (what: string) => z.string().uuid().describe(`The ${what} id`);
const confirmArg = z.boolean().optional().describe("Must be true to actually start. Without it nothing starts and you get a preview with the cost.");

type Shape = z.ZodRawShape;
export interface Tool<S extends Shape = Shape> {
  name: string;
  title: string;
  description: string;
  input: S;
  /** true when it only reads; false when it changes something. */
  readOnly: boolean;
  /** Which kind of account may use it. The API checks this too; checking here gives a clearer message. */
  role: "organizer" | "recruiter" | "any";
  run: (api: TalnexApi, args: z.infer<z.ZodObject<S>>) => Promise<unknown>;
}
const tool = <S extends Shape>(t: Tool<S>): Tool<S> => t;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function askAndWait(api: TalnexApi, path: string, question: string, waitSeconds: number) {
  const asked = await api.call<{ id: string }>(path, { body: { question } });
  const until = Date.now() + waitSeconds * 1000;
  for (;;) {
    const item = await api.call<{ status: string; answer: unknown; error: string | null }>(`/v1/walkthroughs/${asked.id}`);
    if (item.status !== "queued" && item.status !== "running") return item;
    if (Date.now() > until) return { ...item, note: `Still being answered; read it later with id ${asked.id}.` };
    await sleep(2000);
  }
}

/** A clear refusal before calling the API when the tool is for the other kind of account. */
export function roleProblem(t: Pick<Tool, "name" | "role">, role: string): string | null {
  if (t.role === "any" || t.role === role) return null;
  return `${t.name} is for ${t.role} accounts, but this server is set up as a ${role} (TALNEX_ROLE). ` +
    `Start it with TALNEX_ROLE=${t.role} and that person's TALNEX_EMAIL.`;
}

export const TOOLS = [
  tool({
    name: "who_am_i", role: "any", title: "Who am I", readOnly: true, input: {},
    description: "Which TalNex account this server acts as (from TALNEX_EMAIL and TALNEX_ROLE). Use it to check the setup.",
    run: async (api) => ({ ...(await api.call<object>("/v1/me")), role: api.settings.role }),
  }),

  // ---------------------------------------------------------------- organizer
  tool({
    name: "list_events", role: "organizer", title: "List hackathon events", readOnly: true, input: {},
    description: "Organizer: every hackathon event you own, with its type and dates.",
    run: async (api) => {
      const events = await api.call<Record<string, unknown>[]>("/v1/events");
      return events.map(({ id, name, mode, role_level, starts_at, ends_at }) => ({ id, name, mode, role_level, starts_at, ends_at }));
    },
  }),
  tool({
    name: "get_event", role: "organizer", title: "Get an event with its teams", readOnly: true, input: { event_id: id("event") },
    description: "Organizer: one event and every team in it: status, TalNex score out of 10, coverage, weighted total, " +
      "flag counts, and how long its latest check took and what it cost. Teams are listed by name, never ranked.",
    run: (api, a) => api.call(`/v1/events/${a.event_id}/overview`),
  }),
  tool({
    name: "create_event", role: "organizer", title: "Create a hackathon event", readOnly: false,
    input: {
      name: z.string().min(1).max(200),
      mode: z.enum(["open_theme", "fixed_problem"]).describe("open_theme: TalNex reads each team's code for its features. fixed_problem: one problem, scored on your criteria."),
      starts_at: z.string().describe("When the event started, ISO 8601, e.g. 2026-10-23T09:00:00Z"),
      ends_at: z.string().describe("When it ended, ISO 8601"),
      role_level: z.enum(LEVELS).optional().describe("How features are scored. Default fresher."),
      sponsor_tools: z.array(z.string()).optional(),
      criteria: z.array(z.object({ name: z.string(), description: z.string().optional(), weight: z.number().positive() }))
        .optional().describe("fixed_problem only: the judging criteria with weights"),
    },
    description: "Organizer: create a hackathon event. Nothing is checked until you add teams and run them.",
    run: (api, a) => api.call("/v1/events", {
      body: { name: a.name, mode: a.mode, starts_at: a.starts_at, ends_at: a.ends_at, role_level: a.role_level ?? "fresher",
              sponsor_tools: a.sponsor_tools ?? [],
              criteria: (a.criteria ?? []).map((c) => ({ name: c.name, description: c.description ?? "", weight: c.weight })) },
    }),
  }),
  tool({
    name: "add_project", role: "organizer", title: "Add a team to an event", readOnly: false,
    input: {
      event_id: id("event"), team_name: z.string().min(1).max(200),
      live_url: z.string().url().optional(), repo_url: z.string().url().optional(), video_url: z.string().url().optional(),
      team_github_handles: z.array(z.string()).optional(),
    },
    description: "Organizer: add one team (its live site, public GitHub repository and/or demo video; at least one link). " +
      "It is not checked until you run it.",
    run: (api, a) => api.call(`/v1/events/${a.event_id}/projects`, {
      body: { team_name: a.team_name, live_url: a.live_url ?? "", repo_url: a.repo_url ?? "", video_url: a.video_url ?? "",
              team_github_handles: a.team_github_handles ?? [] },
    }),
  }),
  tool({
    name: "run_event", role: "organizer", title: "Check every new team of an event", readOnly: false,
    input: { event_id: id("event"), confirm: confirmArg },
    description: "Organizer: start checking every team not checked yet. SPENDS MONEY (about $0.10–0.15 per team): " +
      "only starts with confirm: true. Without it, returns which teams would be checked and the estimate.",
    run: async (api, a) => {
      if (!a.confirm) {
        const o = await api.call<{ projects: { team_name: string; status: string }[] }>(`/v1/events/${a.event_id}/overview`);
        const fresh = o.projects.filter((p) => p.status === "submitted");
        return { started: false, would_check: fresh.map((p) => p.team_name),
                 already_checked: o.projects.filter((p) => p.status !== "submitted").map((p) => p.team_name),
                 estimate: estimate(fresh.length), how_to_start: "Call run_event again with confirm: true." };
      }
      return { started: true, api_answer: await api.call(`/v1/events/${a.event_id}/run`, { method: "POST" }) };
    },
  }),
  tool({
    name: "run_project", role: "organizer", title: "Check one team", readOnly: false,
    input: { project_id: id("project"), confirm: confirmArg },
    description: "Organizer: check one team now (or again). SPENDS MONEY (about $0.10–0.15): only starts with " +
      "confirm: true. Without it, returns the team's links and the estimate.",
    run: async (api, a) => {
      if (!a.confirm) {
        const p = await api.call<Record<string, unknown>>(`/v1/projects/${a.project_id}`);
        return { started: false, would_check: { team: p.team_name, live_url: p.live_url, repo_url: p.repo_url, video_url: p.video_url, status: p.status },
                 estimate: estimate(1), how_to_start: "Call run_project again with confirm: true." };
      }
      return { started: true, api_answer: await api.call(`/v1/projects/${a.project_id}/run`, { method: "POST" }) };
    },
  }),
  tool({
    name: "get_proof_card", role: "organizer", title: "Get a team's proof card", readOnly: true, input: { project_id: id("project") },
    description: "Organizer: one team's proof card: every claim with its verdict (works, partly works, broken, could not " +
      "test), score out of 10, reason and proof, group scores, red flags (beside the score, never subtracted), the AI " +
      "opinion (not tested proof), checks that did not run, and the run's time and cost.",
    run: (api, a) => api.call(`/v1/projects/${a.project_id}/proof`),
  }),
  tool({
    name: "compare_event", role: "organizer", title: "Who built each feature best", readOnly: true, input: { event_id: id("event") },
    description: "Organizer: for each feature, up to three teams that built it best (never one winner), plus pairs of " +
      "teams whose code looks shared. Ready once every team's check has finished.",
    run: (api, a) => api.call(`/v1/events/${a.event_id}/compare`),
  }),
  tool({
    name: "ask_project", role: "any", title: "Ask how a feature works", readOnly: false,
    input: {
      kind: z.enum(["project", "candidate_project"]).describe("project (hackathon team) or candidate_project (a project on a resume)"),
      project_id: id("project"), question: z.string().min(3).max(500),
      wait_seconds: z.number().int().min(0).max(120).optional().describe("How long to wait for the answer (default 60)"),
    },
    description: "Ask a question about one project (\"How does the login work?\"). The answer comes from the code and the " +
      "test results, with links to the proof. An explanation, never a score.",
    run: (api, a) => askAndWait(api, `/v1/${a.kind === "project" ? "projects" : "candidate-projects"}/${a.project_id}/walkthroughs`,
                                a.question, a.wait_seconds ?? 60),
  }),

  // ---------------------------------------------------------------- recruiter
  tool({
    name: "list_roles", role: "recruiter", title: "List hiring roles", readOnly: true, input: {},
    description: "Recruiter: your hiring roles (a candidate can sit under one). auto_confirm roles start the checks as " +
      "soon as a resume is read.",
    run: (api) => api.call("/v1/roles"),
  }),
  tool({
    name: "list_candidates", role: "recruiter", title: "List candidates", readOnly: true, input: {},
    description: "Recruiter: every candidate you added, with their status.",
    run: (api) => api.call("/v1/candidates"),
  }),
  tool({
    name: "create_candidate", role: "recruiter", title: "Add a candidate and read their resume", readOnly: false,
    input: {
      resume_path: z.string().describe("Path to the resume PDF on this computer (up to 5 MB)"),
      label: z.string().max(200).optional().describe("A label, no real name needed"),
      role_level: z.enum(LEVELS).optional(),
      role_id: z.string().uuid().optional().describe("Put the candidate under this hiring role"),
      coding_handles: z.record(z.string(), z.string()).optional().describe("codeforces / leetcode / codechef handles"),
      confirm: z.boolean().optional().describe("Needed only when the role starts checks automatically (auto_confirm)"),
    },
    description: "Recruiter: add a candidate and upload their resume. TalNex reads it (one small model call) and lists " +
      "the projects it found for you to confirm. If role_id is a role with auto_confirm, the paid checks start by " +
      "themselves, so then confirm: true is required.",
    run: async (api, a) => {
      if (a.role_id) {
        const role = await api.call<{ auto_confirm?: boolean; title?: string }>(`/v1/roles/${a.role_id}`);
        if (role.auto_confirm && !a.confirm) {
          return { started: false, reason: `The role "${role.title}" starts the checks automatically once the resume is read, which spends money.`,
                   estimate: estimate(3), how_to_start: "Call create_candidate again with confirm: true, or use a role without auto confirm." };
        }
      }
      if (!a.resume_path.toLowerCase().endsWith(".pdf")) throw new ApiError("The resume must be a PDF file.", 400);
      let bytes: Buffer;
      try {
        bytes = await readFile(a.resume_path);
      } catch {
        throw new ApiError(`Cannot read the file ${a.resume_path}.`, 400);
      }
      const candidate = await api.call<{ id: string }>("/v1/candidates", {
        // role_id only when given, so an API built before roles existed still accepts the body
        body: { label: a.label ?? "", role_level: a.role_level ?? "fresher", coding_handles: a.coding_handles ?? {},
                ...(a.role_id ? { role_id: a.role_id } : {}) },
      });
      const form = new FormData();
      form.append("resume", new Blob([new Uint8Array(bytes)], { type: "application/pdf" }), basename(a.resume_path));
      const upload = await api.call<object>(`/v1/candidates/${candidate.id}/resume`, { form, timeoutMs: 60_000 });
      return { candidate, upload, next: "Call get_found_projects in a few seconds to see what TalNex found." };
    },
  }),
  tool({
    name: "get_found_projects", role: "recruiter", title: "What TalNex found on a resume", readOnly: true, input: { candidate_id: id("candidate") },
    description: "Recruiter: the projects and coding profiles TalNex read from the resume, waiting for you to confirm.",
    run: (api, a) => api.call(`/v1/candidates/${a.candidate_id}/found`),
  }),
  tool({
    name: "confirm_candidate", role: "recruiter", title: "Confirm and start a candidate's checks", readOnly: false,
    input: {
      candidate_id: id("candidate"),
      projects: z.array(z.object({ name: z.string(), live_url: z.string().optional(), repo_url: z.string().optional(),
                                   video_url: z.string().optional() })).max(8).optional()
        .describe("The projects to check. Leave out to use exactly what TalNex found."),
      coding_profiles: z.record(z.string(), z.string()).optional().describe("site -> handle or profile link; leave out to keep what was found"),
      confirm: confirmArg,
    },
    description: "Recruiter: confirm the found projects and start checking them. SPENDS MONEY (about $0.10–0.15 per " +
      "project): only starts with confirm: true. Without it, returns what would be checked and the estimate.",
    run: async (api, a) => {
      const found = await api.call<{ projects: { name: string; live_url: string; repo_url: string; video_url: string }[]; coding_handles: Record<string, string> }>(
        `/v1/candidates/${a.candidate_id}/found`);
      const projects = (a.projects ?? found.projects).map((p) => ({ name: p.name, live_url: p.live_url ?? "", repo_url: p.repo_url ?? "", video_url: p.video_url ?? "" }));
      const profiles = a.coding_profiles ?? found.coding_handles ?? {};
      if (!a.confirm) {
        return { started: false, would_check: projects, coding_profiles: profiles, estimate: estimate(projects.length),
                 how_to_start: "Call confirm_candidate again with confirm: true." };
      }
      return { started: true, api_answer: await api.call(`/v1/candidates/${a.candidate_id}/confirm`, { body: { projects, coding_profiles: profiles } }) };
    },
  }),
  tool({
    name: "get_progress", role: "recruiter", title: "A candidate's progress", readOnly: true, input: { candidate_id: id("candidate") },
    description: "Recruiter: where each stage of a candidate's check stands, per project.",
    run: (api, a) => api.call(`/v1/candidates/${a.candidate_id}/progress`),
  }),
  tool({
    name: "get_report", role: "recruiter", title: "A candidate's proof report", readOnly: true, input: { candidate_id: id("candidate") },
    description: "Recruiter: the proof report: each resume project's claims with verdicts, scores out of 10, reasons and " +
      "proof, originality, code history, coding-profile signals, time saved and the run's cost.",
    run: (api, a) => api.call(`/v1/candidates/${a.candidate_id}/report`),
  }),
  tool({
    name: "delete_candidate", role: "recruiter", title: "Delete a candidate and their files", readOnly: false,
    input: { candidate_id: id("candidate"), confirm: z.boolean().optional().describe("Must be true: this cannot be undone") },
    description: "Recruiter: permanently delete a candidate, their resume file, results and screenshots. Cannot be undone, " +
      "so it only happens with confirm: true.",
    run: async (api, a) => {
      if (!a.confirm) return { deleted: false, note: "Nothing deleted. Call again with confirm: true to delete for good." };
      await api.call(`/v1/candidates/${a.candidate_id}`, { method: "DELETE" });
      return { deleted: true };
    },
  }),

  // ---------------------------------------------------------------- live
  tool({
    name: "watch_live", role: "any", title: "Watch a check live", readOnly: true,
    input: {
      kind: z.enum(LIVE_KINDS as unknown as [string, ...string[]]).describe("project, candidate_project, candidate or event"),
      id: z.string().uuid().describe("The id of that project, candidate or event"),
      seconds: z.number().int().min(1).max(120).optional().describe("How long to watch (default 20, at most 120)"),
    },
    description: "Watch what TalNex is doing right now (saved events are replayed first), then get a digest per team " +
      "or project: stages, each claim's status or verdict so far, the latest actions and the agent's reasons, and the " +
      "browser cost. A claim is only ever 'broken' once its verdict arrives.",
    run: (api, a) => watchLive(api, a.kind as (typeof LIVE_KINDS)[number], a.id, a.seconds ?? 20),
  }),
];
