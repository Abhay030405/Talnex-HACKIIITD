// The live view: what TalNex is doing right now, from the event stream the Go API sends (docs/live_events.md).
// Pure state code, safe for the browser: one reducer folds each event into the view, so it can be tested without a
// stream. Everything in an event is text from the outside world and is only ever shown as plain text.

export const LIVE_KINDS = ["project", "candidate_project", "candidate", "event"] as const;
export type LiveKind = (typeof LIVE_KINDS)[number];

export function isLiveKind(value: unknown): value is LiveKind {
  return typeof value === "string" && (LIVE_KINDS as readonly string[]).includes(value);
}

/** The event kinds the stream sends, in the order they usually arrive. */
export const EVENT_KINDS = [
  "stage.started",
  "stage.finished",
  "stage.failed",
  "claims.queued",
  "claim.started",
  "ladder",
  "run.started",
  "reason",
  "step.record",
  "step.result",
  "run.outcome",
  "run.finished",
  "check.started",
  "check",
  "verdict",
] as const;

export interface LiveEvent {
  kind?: string;
  at?: string;
  subject?: { kind?: string; id?: string };
  stage?: string;
  claim_id?: string;
  data?: Record<string, unknown>;
}

export type StageState = "running" | "done" | "skipped" | "failed" | "retrying";
export type ClaimState = "queued" | "testing" | "works" | "partly_works" | "broken" | "could_not_test" | "reviewed_from_code";

export interface LiveClaim {
  text: string;
  status: ClaimState;
  confidence?: string;
  reason?: string;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LogLine {
  at: string;
  label: string;
  text: string;
  tone: "plain" | "reason" | "works" | "partly" | "broken" | "unknown" | "failed";
}

export interface LiveSubject {
  id: string;
  kind: string;
  stages: [string, StageState][];
  current: string;
  claims: Record<string, LiveClaim>;
  claimOrder: string[];
  shot: { url: string; box?: Box } | null;
  label: string;
  reason: string;
  url: string;
  actions: number;
  log: LogLine[];
}

export interface LiveState {
  subjects: Record<string, LiveSubject>;
  order: string[];
  actions: number;
  costUsd: number;
  verdicts: number;
}

export const LOG_LIMIT = 300;

export const emptyLiveState = (): LiveState => ({ subjects: {}, order: [], actions: 0, costUsd: 0, verdicts: 0 });

const STAGE_WORDS: Record<string, string> = {
  precheck: "checking the site",
  claims: "reading the claims",
  test_plan: "planning the tests",
  live_test: "testing the live site",
  proof_check: "checking the proof",
  feature_score: "scoring",
  project_score: "scoring",
  project_report: "writing the proof card",
  feature_compare: "comparing teams",
  ai_opinion: "AI opinion",
  resume_read: "reading the resume",
  candidate_report: "writing the report",
};

export function stageWord(stage: string): string {
  return STAGE_WORDS[stage] ?? stage.replaceAll("_", " ");
}

const VERDICT_WORDS: Record<string, string> = {
  queued: "waiting",
  testing: "testing…",
  works: "works",
  partly_works: "partly works",
  broken: "broken",
  could_not_test: "could not test",
  reviewed_from_code: "reviewed from code",
};

export function claimWord(status: string): string {
  return VERDICT_WORDS[status] ?? status.replaceAll("_", " ");
}

const VERDICTS = new Set(["works", "partly_works", "broken", "could_not_test", "reviewed_from_code"]);

function text(value: unknown): string {
  return typeof value === "string" ? value : value === undefined || value === null ? "" : String(value);
}

function num(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

function asBox(value: unknown): Box | undefined {
  if (!value || typeof value !== "object") return undefined;
  const b = value as Record<string, unknown>;
  const box = { x: num(b.x), y: num(b.y), w: num(b.w), h: num(b.h) };
  return box.w > 0 && box.h > 0 ? box : undefined;
}

function safeUrl(value: unknown): string {
  const url = text(value);
  return /^https?:\/\//i.test(url) ? url : "";
}

function newSubject(id: string, kind: string): LiveSubject {
  return {
    id,
    kind,
    stages: [],
    current: "",
    claims: {},
    claimOrder: [],
    shot: null,
    label: "",
    reason: "",
    url: "",
    actions: 0,
    log: [],
  };
}

function setStage(stages: [string, StageState][], name: string, state: StageState): [string, StageState][] {
  const i = stages.findIndex(([n]) => n === name);
  if (i === -1) return [...stages, [name, state]];
  const next = stages.slice();
  next[i] = [name, state];
  return next;
}

function withClaim(s: LiveSubject, id: string | undefined, change: (c: LiveClaim) => LiveClaim): LiveSubject {
  if (!id) return s;
  const known = s.claims[id];
  const claim = change(known ?? { text: "", status: "queued" });
  return {
    ...s,
    claims: { ...s.claims, [id]: claim },
    claimOrder: known ? s.claimOrder : [...s.claimOrder, id],
  };
}

function verdictTone(verdict: string): LogLine["tone"] {
  if (verdict === "works") return "works";
  if (verdict === "broken") return "broken";
  if (verdict === "partly_works") return "partly";
  return "unknown";
}

/** Folds one event into the view. Unknown kinds or events without a subject change nothing. */
export function reduceLive(state: LiveState, kind: string, ev: LiveEvent): LiveState {
  const id = ev.subject?.id;
  if (!id) return state;
  const d = ev.data ?? {};
  let s = state.subjects[id] ?? newSubject(id, text(ev.subject?.kind) || "project");
  let { actions, costUsd, verdicts } = state;
  const stage = text(ev.stage);
  let line: Omit<LogLine, "at"> | null = null;

  switch (kind) {
    case "stage.started":
      s = { ...s, stages: setStage(s.stages, stage, "running"), current: stageWord(stage) };
      line = { label: stage, text: "started", tone: "plain" };
      break;
    case "stage.finished": {
      const skipped = d.skipped === true;
      s = {
        ...s,
        stages: setStage(s.stages, stage, skipped ? "skipped" : "done"),
        current: s.current === stageWord(stage) ? "" : s.current,
      };
      line = { label: stage, text: skipped ? `skipped: ${text(d.reason)}` : "done", tone: "plain" };
      break;
    }
    case "stage.failed": {
      const retrying = text(d.status) === "retrying";
      s = { ...s, stages: setStage(s.stages, stage, retrying ? "retrying" : "failed") };
      line = { label: stage, text: `${retrying ? "will retry" : "failed"}: ${text(d.error)}`, tone: "failed" };
      break;
    }
    case "claims.queued":
      for (const c of Array.isArray(d.claims) ? d.claims : []) {
        const claim = c as { id?: unknown; text?: unknown };
        const cid = text(claim.id);
        if (cid && !s.claims[cid]) s = withClaim(s, cid, () => ({ text: text(claim.text), status: "queued" }));
      }
      line = { label: "claims", text: `${num(d.total)} to test`, tone: "plain" };
      break;
    case "claim.started":
      // A claim only ever shows "testing" until its verdict arrives: never "broken" before the never-blame ladder ends.
      s = withClaim(s, ev.claim_id, (c) => ({
        ...c,
        text: text(d.text) || c.text,
        status: VERDICTS.has(c.status) ? c.status : "testing",
      }));
      line = { label: "testing", text: text(d.text), tone: "plain" };
      break;
    case "reason":
      s = { ...s, reason: text(d.text) };
      line = { label: "why", text: text(d.text), tone: "reason" };
      break;
    case "step.record": {
      const url = safeUrl(d.proof_url);
      actions += 1;
      s = {
        ...s,
        actions: s.actions + 1,
        label: text(d.label),
        url: safeUrl(d.url),
        shot: url ? { url, box: asBox(d.box) } : s.shot,
      };
      line = { label: "step", text: text(d.label), tone: "plain" };
      break;
    }
    case "step.result":
      line = { label: "result", text: `step ${num(d.step)} of ${num(d.steps)}: ${text(d.result)}`, tone: "plain" };
      break;
    case "ladder":
      line = { label: "ladder", text: text(d.line), tone: "plain" };
      break;
    case "run.started":
      line = { label: "browser", text: `try ${num(d.try_number) || 1}, ${text(d.test_type) || "normal"} test`, tone: "plain" };
      break;
    case "run.finished":
      costUsd += num(d.cost_usd);
      line = { label: "browser", text: `closed: ${text(d.outcome)}`, tone: "plain" };
      break;
    case "check.started":
      line = { label: "check", text: `a separate AI looks at ${num(d.images)} screenshots`, tone: "plain" };
      break;
    case "check":
      line = { label: "check", text: `${text(d.outcome)}: ${text(d.seen)}`, tone: "plain" };
      break;
    case "verdict": {
      const verdict = text(d.verdict);
      if (!VERDICTS.has(verdict)) return state;
      verdicts += 1;
      s = withClaim(s, ev.claim_id, (c) => ({
        ...c,
        status: verdict as ClaimState,
        confidence: text(d.confidence) || undefined,
        reason: text(d.reason) || undefined,
      }));
      line = { label: claimWord(verdict), text: text(d.reason), tone: verdictTone(verdict) };
      break;
    }
    default:
      return state;
  }

  if (line) s = { ...s, log: [...s.log, { at: text(ev.at), ...line }].slice(-LOG_LIMIT) };
  return {
    subjects: { ...state.subjects, [id]: s },
    order: state.order.includes(id) ? state.order : [...state.order, id],
    actions,
    costUsd,
    verdicts,
  };
}

/** How many claims of a subject are in each state, for its panel header. */
export function tally(s: LiveSubject): { total: number; works: number; broken: number; other: number; testing: number } {
  const t = { total: s.claimOrder.length, works: 0, broken: 0, other: 0, testing: 0 };
  for (const id of s.claimOrder) {
    const status = s.claims[id]?.status;
    if (status === "works") t.works += 1;
    else if (status === "broken") t.broken += 1;
    else if (status === "testing") t.testing += 1;
    else if (status && status !== "queued") t.other += 1;
  }
  return t;
}

/** The time of an event as HH:MM:SS in the viewer's clock, or "" when it can't be read. */
export function clock(at: string): string {
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? "" : d.toTimeString().slice(0, 8);
}

export function formatUsd(value: number): string {
  return `$${value.toFixed(4)}`;
}

/** Where the Go API serves the stream for one subject. */
export function liveApiPath(kind: LiveKind, id: string): string {
  return `/v1/live/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`;
}
