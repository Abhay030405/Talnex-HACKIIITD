// Helpers for "Ask about this feature": shared by the box in the browser and the server routes that carry its
// questions to the API. Nothing here is secret.
import { fileLabel } from "@/lib/authorship-format";
import type { ProofRef, WalkthroughMissing, WalkthroughStatus, WalkthroughSubject } from "@/lib/types";

/** How often the box asks whether the answer is ready, and when it stops asking. */
export const POLL_EVERY_MS = 1500;
export const POLL_GIVE_UP_MS = 3 * 60 * 1000;
/** The API keeps typed questions up to this length (backend/internal/http/walkthrough.go). */
export const MAX_QUESTION_CHARS = 2000;

/** Every answer shows this label, even if a stored answer lost it. */
export const DEFAULT_LABEL = "AI explanation of the evidence — the proof is in the links.";

/** What browsers can record, in order of preference. The API accepts all of them. Safari only records MP4. */
export const RECORDING_TYPES = ["audio/webm", "audio/ogg", "audio/mp4"] as const;

const SUBJECT_PATHS: Record<WalkthroughSubject, string> = {
  project: "projects",
  candidate_project: "candidate-projects",
};

export function isSubject(value: unknown): value is WalkthroughSubject {
  return value === "project" || value === "candidate_project";
}

/** The API path that lists and takes questions about one project. */
export function walkthroughsPath(subject: WalkthroughSubject, subjectId: string): string {
  return `/v1/${SUBJECT_PATHS[subject]}/${encodeURIComponent(subjectId)}/walkthroughs`;
}

export function isFinished(status: WalkthroughStatus): boolean {
  return status === "done" || status === "failed";
}

const STATUS_WORDS: Record<WalkthroughStatus, string> = {
  queued: "Waiting to start…",
  answering: "Reading the code and the test results…",
  done: "Answered",
  failed: "Could not answer",
};

export function walkthroughStatusWords(status: WalkthroughStatus): string {
  return STATUS_WORDS[status] ?? "Working on it…";
}

const MISSING_WORDS: Record<WalkthroughMissing["status"], string> = {
  not_found_in_code: "Not found in the code",
  code_not_readable: "The code could not be read",
};

export function missingStatusWords(status: string): string {
  return MISSING_WORDS[status as WalkthroughMissing["status"]] ?? status.replace(/_/g, " ");
}

/** A short name for a proof link, and where it leads (or null when it is a note, not a link). */
export function refInfo(ref: ProofRef): { label: string; url: string | null; note?: string } {
  switch (ref.kind) {
    case "code":
      return { label: fileLabel(ref), url: ref.url || null };
    case "screenshot":
      return { label: "Screenshot", url: ref.view_url || null };
    case "step":
      return { label: "Test step", url: null };
    case "review":
      return { label: "Code review note", url: null, note: ref.note };
    case "authorship":
      return { label: "Who wrote it", url: null };
    default:
      return { label: "Proof", url: null };
  }
}

/** The question sent when the reader picks one of the offered features. */
export function choiceQuestion(text: string): string {
  return `Walk me through: ${text}`;
}

/** A typed question, trimmed and kept within the API's limit; empty means nothing to ask. */
export function cleanQuestion(value: unknown): string {
  return typeof value === "string" ? value.trim().slice(0, MAX_QUESTION_CHARS) : "";
}

/** The first recording type this browser supports, or null when it cannot record at all. */
export function pickRecordingType(isSupported: ((type: string) => boolean) | undefined): string | null {
  if (!isSupported) return null;
  return RECORDING_TYPES.find((type) => isSupported(type)) ?? null;
}
