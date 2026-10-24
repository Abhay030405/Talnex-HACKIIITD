// The guided tour page (architecture section 32): a chat on the left, the live site on the right. Pure helpers, safe for
// the browser: one reducer folds each live event of one tour into what the page shows, so it can be tested without a
// stream. Everything in an event is text from the outside world and is only ever shown as plain text.
import type { Box } from "@/lib/live";
import type { WalkthroughSubject } from "@/lib/types";
import { isSubject } from "@/lib/walkthrough-format";

export { isSubject };

/** The event kinds a tour sends, besides the step records the browser steps share with the tests. */
export const TOUR_EVENT_KINDS = [
  "tour.started",
  "tour.status",
  "tour.read",
  "tour.say",
  "tour.code",
  "tour.notice",
  "tour.done",
  "step.record",
] as const;

/** The API keeps questions up to this long (backend/internal/http/walkthrough.go). */
export const MAX_TOUR_QUESTION_CHARS = 2000;
export const TOUR_LABEL = "AI explanation of the evidence — the proof is in the links.";

const SUBJECT_PATHS: Record<WalkthroughSubject, string> = { project: "projects", candidate_project: "candidate-projects" };

/** The API path that opens a chat for one project. */
export const tourStartPath = (subject: WalkthroughSubject, subjectId: string) =>
  `/v1/${SUBJECT_PATHS[subject]}/${encodeURIComponent(subjectId)}/tours`;
export const tourPath = (tourId: string) => `/v1/tours/${encodeURIComponent(tourId)}`;
export const tourMessagesPath = (tourId: string) => `${tourPath(tourId)}/messages`;

/** The website page of one project's walk-through. */
export function tourPageUrl(subject: WalkthroughSubject, subjectId: string, parent: string, tourId?: string): string {
  const base =
    subject === "project"
      ? `/events/${encodeURIComponent(parent)}/projects/${encodeURIComponent(subjectId)}/walkthrough`
      : `/candidates/${encodeURIComponent(parent)}/projects/${encodeURIComponent(subjectId)}/walkthrough`;
  return tourId ? `${base}?tour=${encodeURIComponent(tourId)}` : base;
}

export function cleanTourQuestion(value: unknown): string {
  return typeof value === "string" ? value.trim().slice(0, MAX_TOUR_QUESTION_CHARS) : "";
}

/** Whether a tour id from the address bar looks like one (the API answers "not found" to anything else). */
export const isTourId = (value: unknown): value is string =>
  typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

// ---------- what the API and the stream send ----------

export interface TourProof {
  kind: string;
  file?: string;
  start?: number;
  end?: number;
  commit?: string | null;
  url?: string | null;
  view_url?: string | null;
  lines?: string[];
}

export interface TourSay {
  text: string;
  proof: TourProof[];
  shown?: boolean | null;
  note?: string | null;
}

export type TourMessageStatus = "queued" | "working" | "done" | "failed";

export interface TourMessage {
  id: string;
  question: string;
  status: TourMessageStatus;
  answer: { say: TourSay[]; label?: string; mode?: string } | null;
  error: string | null;
  created_at: string;
  answered_at: string | null;
}

export interface Tour {
  id: string;
  subject: { kind: string; id: string };
  messages: TourMessage[];
}

export interface TourEvent {
  kind?: string;
  tour_id?: string;
  message_id?: string;
  data?: Record<string, unknown>;
}

// ---------- the live part of a chat ----------

export interface LiveSay {
  index: number;
  text: string;
  proof: TourProof[];
  /** The code lines behind the sentence, once the guide has shown them. */
  snippets: TourProof[];
  note: string | null;
}

export interface TourShot {
  /** A short-lived view link made by the API; the page never sees a storage key. */
  url: string | null;
  box: Box | null;
  label: string;
  page: string;
}

export interface TourLive {
  messageId: string | null;
  status: string;
  reads: string[];
  says: LiveSay[];
  shot: TourShot | null;
  notices: string[];
  finished: "done" | "failed" | null;
}

export const MAX_READS_SHOWN = 6;

export function emptyTourLive(): TourLive {
  return { messageId: null, status: "", reads: [], says: [], shot: null, notices: [], finished: null };
}

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const whole = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const list = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.filter((v): v is Record<string, unknown> => !!v && typeof v === "object") : [];

function readBox(value: unknown): Box | null {
  if (!value || typeof value !== "object") return null;
  const box = value as Record<string, unknown>;
  const [x, y, w, h] = [whole(box.x), whole(box.y), whole(box.w), whole(box.h)];
  return x === null || y === null || w === null || h === null || w <= 0 || h <= 0 ? null : { x, y, w, h };
}

const toProof = (item: Record<string, unknown>): TourProof => ({
  kind: "code",
  file: text(item.file),
  start: whole(item.start) ?? undefined,
  end: whole(item.end) ?? undefined,
  commit: text(item.commit) || null,
  url: text(item.url) || null,
  lines: Array.isArray(item.lines) ? item.lines.filter((l): l is string => typeof l === "string") : [],
});

/**
 * Folds one event of this tour into the live part of the chat. Events of other tours (the stream carries the whole
 * project) and kinds it does not know change nothing. A new message starts the live part again, but keeps the last
 * picture so the browser side is never blank between questions.
 */
export function reduceTour(state: TourLive, kind: string, event: TourEvent, tourId: string): TourLive {
  if (event.tour_id !== tourId) return state;
  if (!(TOUR_EVENT_KINDS as readonly string[]).includes(kind)) return state;
  const data = event.data ?? {};
  const incoming = event.message_id ?? null;
  if (incoming && incoming !== state.messageId) state = { ...emptyTourLive(), messageId: incoming, shot: state.shot };
  switch (kind) {
    case "tour.status":
      return { ...state, status: text(data.text) };
    case "tour.read": {
      const what = `${text(data.tool)} ${text(data.what)}`.trim();
      return { ...state, status: `Reading ${text(data.what)}`, reads: [...state.reads, what].slice(-MAX_READS_SHOWN) };
    }
    case "tour.say": {
      const index = whole(data.index) ?? state.says.length + 1;
      if (state.says.some((s) => s.index === index)) return state;
      const proof = list(data.proof).map(toProof);
      return { ...state, status: "", says: [...state.says, { index, text: text(data.text), proof, snippets: [], note: null }] };
    }
    case "tour.code": {
      const index = whole(data.index);
      const snippets = list(data.snippets).map(toProof);
      return { ...state, says: state.says.map((s) => (s.index === index ? { ...s, snippets } : s)) };
    }
    case "tour.notice": {
      const note = text(data.text);
      const index = whole(data.index);
      if (!note) return state;
      if (index === null) return { ...state, notices: state.notices.includes(note) ? state.notices : [...state.notices, note] };
      return { ...state, says: state.says.map((s) => (s.index === index ? { ...s, note } : s)) };
    }
    case "step.record": {
      const url = text(data.proof_url) || null;
      if (!url) return state;
      return { ...state, shot: { url, box: readBox(data.box), label: text(data.label), page: text(data.url) } };
    }
    case "tour.done":
      return { ...state, status: "", finished: data.status === "failed" ? "failed" : "done" };
    default:
      return state;
  }
}

/** The words shown while the guide works. */
export function workingWords(state: TourLive): string {
  if (state.finished) return "";
  return state.status || (state.messageId ? "Thinking…" : "");
}

/** A short name for a piece of code proof: the file and its lines. */
export function codeLabel(proof: TourProof): string {
  const file = proof.file || "code";
  if (!proof.start) return file;
  return proof.end && proof.end !== proof.start ? `${file}, lines ${proof.start} to ${proof.end}` : `${file}, line ${proof.start}`;
}
