// Calls the Go API from the website's server. The browser never talks to the API directly, so no key or token
// ever reaches it.
import "server-only";

import { redirect } from "next/navigation";

import { env } from "@/lib/env";
import { signApiToken } from "@/lib/token";

/** A call the API refused or could not answer. `message` is safe to show to the person. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Who the call is made for. The API finds or creates the account from the email. */
export interface ApiCaller {
  email: string;
  name?: string | null;
  role?: string | null;
}

export interface ApiRequest {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Sent as JSON. The API refuses fields it does not know, so send exactly its shape. */
  body?: unknown;
  /** Sent as a multipart form, for file uploads. */
  form?: FormData;
  /** Gives up after this long. Uploads may need longer than the default. */
  timeoutMs?: number;
}

export interface ApiDeps {
  baseUrl: string;
  secret: string;
  fetch: typeof fetch;
}

export const DEFAULT_TIMEOUT_MS = 20_000;

const defaultDeps = (): ApiDeps => ({ baseUrl: env.apiBaseUrl, secret: env.authSecret, fetch });

/**
 * One call to the API on behalf of `caller`. Returns the parsed JSON, or null for an empty answer.
 * Every failure becomes an ApiError with words a person can read, never a raw parse or network error.
 */
export async function callApi<T>(
  caller: ApiCaller,
  path: string,
  request: ApiRequest = {},
  deps: ApiDeps = defaultDeps(),
): Promise<T> {
  if (!path.startsWith("/")) throw new Error(`API paths start with "/": ${path}`);
  const token = await signApiToken(deps.secret, caller.email, caller.name, caller.role);
  const headers: Record<string, string> = { Authorization: `Bearer ${token}`, Accept: "application/json" };
  // A form upload sets its own content type, with the boundary, so only JSON bodies get one here.
  if (request.body !== undefined && !request.form) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await deps.fetch(`${deps.baseUrl}${path}`, {
      method: request.method ?? (request.body !== undefined || request.form ? "POST" : "GET"),
      headers,
      body: request.form ?? (request.body === undefined ? undefined : JSON.stringify(request.body)),
      cache: "no-store",
      signal: AbortSignal.timeout(request.timeoutMs ?? DEFAULT_TIMEOUT_MS),
    });
  } catch (e) {
    const timedOut = e instanceof Error && e.name === "TimeoutError";
    throw new ApiError(
      timedOut ? "The TalNex server took too long to answer. Try again." : "Cannot reach the TalNex server.",
      timedOut ? 504 : 503,
    );
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      // Not JSON: a proxy error page or similar. Only the status means anything then.
      if (response.ok) throw new ApiError("The TalNex server sent an answer that could not be read.", 502);
    }
  }
  if (!response.ok) throw new ApiError(errorMessage(data, response.status), response.status);
  return data as T;
}

/**
 * A call for whoever is signed in. A signed-out person, or one the API no longer accepts, is sent to sign in.
 * Other failures throw ApiError for the page to show.
 */
export async function apiFetch<T>(path: string, request: ApiRequest = {}): Promise<T> {
  // Loaded here, not at the top: sign-in itself uses this file, and a top-level import would make a loop.
  const { auth } = await import("@/auth");
  const session = await auth();
  const user = session?.user;
  if (!user?.email) redirect("/login");
  try {
    return await callApi<T>({ email: user.email, name: user.name, role: user.role }, path, request);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect(user.role ? `/login/${user.role}` : "/login");
    throw e;
  }
}

function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && typeof (data as { error?: unknown }).error === "string") {
    return (data as { error: string }).error;
  }
  if (status === 401) return "Please sign in again.";
  if (status === 403) return "This is not yours to open.";
  if (status === 404) return "Not found.";
  if (status >= 500) return `The TalNex server had a problem (error ${status}). Try again.`;
  return `The request was refused (error ${status}).`;
}
