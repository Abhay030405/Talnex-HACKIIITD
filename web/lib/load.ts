// Loading data for a page: either the data, or a problem in words for the page to show instead of crashing.
import "server-only";

import { unstable_rethrow } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";

export type Loaded<T> = { data: T; problem: null } | { data: null; problem: string };

/** `what` names the thing in the message, like "your candidates". */
export async function load<T>(path: string, what: string): Promise<Loaded<T>> {
  try {
    return { data: await apiFetch<T>(path), problem: null };
  } catch (error) {
    // Next's own redirects and not-found travel as errors; they must go on, not become a message.
    unstable_rethrow(error);
    return { data: null, problem: problemText(error, what) };
  }
}

export function problemText(error: unknown, what: string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return `${error.message}. Sign out and use the other sign-in.`;
    if (error.status === 404) return `We could not find ${what}.`;
    if (error.status === 503 || error.status === 504) return `${error.message} Please try again in a moment.`;
  }
  return `We could not load ${what} right now. Please try again in a moment.`;
}
