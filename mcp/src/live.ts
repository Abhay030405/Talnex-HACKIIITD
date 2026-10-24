// Watching a check live: read the Server-Sent Events stream from GET /v1/live/{kind}/{id} for a while, then fold the
// events (docs/live_events.md) into a short digest per subject that an assistant can read in one go.
import { ApiError, errorMessage, type TalnexApi } from "./api.js";

export type LiveKind = "project" | "candidate_project" | "candidate" | "event";
export const LIVE_KINDS: readonly LiveKind[] = ["project", "candidate_project", "candidate", "event"];

export interface LiveEvent {
  kind: string;
  at?: string;
  subject?: { kind?: string; id?: string };
  stage?: string;
  claim_id?: string;
  data?: Record<string, unknown>;
}

export interface ClaimDigest {
  text: string;
  status: string; // queued | testing | works | partly_works | broken | could_not_test | reviewed_from_code
  confidence?: string;
  reason?: string;
}

export interface SubjectDigest {
  kind: string;
  id: string;
  stages: Record<string, string>; // stage -> running | done | skipped | failed | retrying
  now: string;
  claims: Record<string, ClaimDigest>;
  actions: number;
  browser_cost_usd: number;
  last_actions: string[];
  last_reasons: string[];
}

export interface LiveDigest {
  watched_seconds: number;
  events: number;
  subjects: SubjectDigest[];
}

const KEEP = 5;
const str = (v: unknown): string => (typeof v === "string" ? v : v == null ? "" : String(v));
const keepLast = (list: string[], item: string): string[] => (item ? [...list, item].slice(-KEEP) : list);

/** Fold events into one digest per subject. Pure: no network. "broken" only ever comes from a verdict event. */
export function foldLive(events: LiveEvent[]): SubjectDigest[] {
  const subjects = new Map<string, SubjectDigest>();
  for (const ev of events) {
    const id = ev.subject?.id;
    if (!id) continue;
    let s = subjects.get(id);
    if (!s) {
      s = { kind: str(ev.subject?.kind) || "project", id, stages: {}, now: "", claims: {}, actions: 0,
            browser_cost_usd: 0, last_actions: [], last_reasons: [] };
      subjects.set(id, s);
    }
    const d = ev.data ?? {};
    const claim = (cid?: string): ClaimDigest | null => {
      if (!cid) return null;
      s!.claims[cid] ??= { text: "", status: "queued" };
      return s!.claims[cid];
    };
    switch (ev.kind) {
      case "stage.started":
        if (ev.stage) s.stages[ev.stage] = "running";
        s.now = ev.stage ?? s.now;
        break;
      case "stage.finished":
        if (ev.stage) s.stages[ev.stage] = d.skipped === true ? "skipped" : "done";
        if (s.now === ev.stage) s.now = "";
        break;
      case "stage.failed":
        if (ev.stage) s.stages[ev.stage] = d.status === "retrying" ? "retrying" : "failed";
        break;
      case "claims.queued":
        for (const c of (Array.isArray(d.claims) ? d.claims : []) as { id?: string; text?: string }[]) {
          const x = claim(c.id);
          if (x && !x.text) x.text = str(c.text);
        }
        break;
      case "claim.started": {
        const x = claim(ev.claim_id);
        if (x) {
          x.text = str(d.text) || x.text;
          x.status = "testing";
        }
        break;
      }
      case "reason":
        s.last_reasons = keepLast(s.last_reasons, str(d.text));
        break;
      case "step.record":
        s.actions += 1;
        s.last_actions = keepLast(s.last_actions, str(d.label));
        break;
      case "run.finished":
        s.browser_cost_usd = Math.round((s.browser_cost_usd + (Number(d.cost_usd) || 0)) * 1e6) / 1e6;
        break;
      case "verdict": {
        const x = claim(ev.claim_id);
        if (x) {
          x.status = str(d.verdict) || x.status;
          x.confidence = str(d.confidence) || undefined;
          x.reason = str(d.reason).slice(0, 300) || undefined;
        }
        break;
      }
      default:
        break;
    }
  }
  return [...subjects.values()];
}

/** Split an SSE text into events. Returns the parsed events and any unfinished tail to keep for the next chunk.
 * A "replay.start" marker is kept (the watcher starts its list again there); "replay.done" and pings are dropped. */
export function parseSse(buffer: string): { events: LiveEvent[]; rest: string } {
  const events: LiveEvent[] = [];
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let name = "";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (name === "replay.start") {
      events.push({ kind: "replay.start" });
      continue;
    }
    if (!name || name.startsWith("replay.") || data.length === 0) continue;
    try {
      const parsed = JSON.parse(data.join("\n")) as LiveEvent;
      events.push({ ...parsed, kind: parsed.kind || name });
    } catch {
      // a broken line is skipped; watching must never fail because of one event
    }
  }
  return { events, rest };
}

export const MAX_WATCH_SECONDS = 120;
const MAX_RECONNECTS = 5;

/** How long a watch really lasts: at least 1 second, at most 120, whatever was asked. */
export const watchSeconds = (asked: number): number =>
  Math.min(Math.max(Number.isFinite(asked) ? asked : 1, 1), MAX_WATCH_SECONDS);

/** Watch for `seconds` (at most 120; the saved events are replayed first), then return the digest. If the stream
 * drops early it reconnects; each connection replays from the start, so the list starts again at "replay.start". */
export async function watchLive(api: TalnexApi, kind: LiveKind, id: string, seconds: number,
                                fetchFn: typeof fetch = fetch): Promise<LiveDigest & { reconnects: number }> {
  const started = Date.now();
  const deadline = started + watchSeconds(seconds) * 1000;
  let events: LiveEvent[] = [];
  let reconnects = 0;
  let connected = false;
  let lastProblem = "";
  const url = `${api.settings.apiUrl}/v1/live/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`;

  while (Date.now() < deadline) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(0, deadline - Date.now()));
    try {
      const response = await fetchFn(url, { headers: { ...(await api.headers()), Accept: "text/event-stream" }, signal: controller.signal });
      if (!response.ok || !response.body) {
        const text = await response.text().catch(() => "");
        let data: unknown = null;
        try {
          data = JSON.parse(text);
        } catch { /* not JSON */ }
        throw new ApiError(errorMessage(data, response.status), response.status);
      }
      connected = true;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSse(buffer);
        for (const ev of parsed.events) {
          if (ev.kind === "replay.start") events = [];
          else events.push(ev);
        }
        buffer = parsed.rest;
      }
    } catch (e) {
      const aborted = e instanceof Error && e.name === "AbortError";
      if (!aborted) {
        if (e instanceof ApiError) throw e;
        lastProblem = e instanceof Error ? e.message : String(e);
      }
    } finally {
      clearTimeout(timer);
    }
    if (Date.now() >= deadline) break;
    // the stream ended or dropped before the time was up: try again, a short moment later
    if (reconnects >= MAX_RECONNECTS) break;
    reconnects += 1;
    await new Promise((r) => setTimeout(r, Math.min(500, Math.max(0, deadline - Date.now()))));
  }
  if (!connected) {
    throw new ApiError(`Cannot reach the TalNex live stream at ${api.settings.apiUrl}${lastProblem ? ` (${lastProblem})` : ""}.`, 503);
  }
  return { watched_seconds: Math.round((Date.now() - started) / 1000), events: events.length, reconnects, subjects: foldLive(events) };
}
