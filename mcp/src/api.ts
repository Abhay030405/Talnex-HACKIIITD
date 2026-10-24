// Calls the TalNex Go API, signed the same way the website signs its calls (web/lib/token.ts): HS256 with
// AUTH_SECRET, the person's email and role, and a two-minute expiry. Signing with the shared secret is for local and
// self-hosted use; per-person API keys are future work.
import { SignJWT } from "jose";

import type { Settings } from "./settings.js";

export const API_TOKEN_SECONDS = 120;
export const DEFAULT_TIMEOUT_MS = 20_000;

/** A call the API refused or could not answer. `message` is plain words, safe to show. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function signApiToken(secret: string, email: string, role?: string | null): Promise<string> {
  const clean = email.trim().toLowerCase();
  if (!clean) throw new Error("An API token needs the person's email");
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ email: clean, name: "", ...(role ? { role } : {}) })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuedAt(now)
    .setExpirationTime(now + API_TOKEN_SECONDS)
    .sign(new TextEncoder().encode(secret));
}

export interface ApiRequest {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  form?: FormData;
  timeoutMs?: number;
}

export class TalnexApi {
  constructor(
    readonly settings: Settings,
    private readonly fetchFn: typeof fetch = fetch,
  ) {}

  async headers(): Promise<Record<string, string>> {
    const token = await signApiToken(this.settings.secret, this.settings.email, this.settings.role);
    return { Authorization: `Bearer ${token}`, Accept: "application/json" };
  }

  /** One call. Returns the parsed JSON (null for an empty answer); every failure is an ApiError in plain words. */
  async call<T = unknown>(path: string, request: ApiRequest = {}): Promise<T> {
    const headers = await this.headers();
    if (request.body !== undefined && !request.form) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await this.fetchFn(`${this.settings.apiUrl}${path}`, {
        method: request.method ?? (request.body !== undefined || request.form ? "POST" : "GET"),
        headers,
        body: request.form ?? (request.body === undefined ? undefined : JSON.stringify(request.body)),
        signal: AbortSignal.timeout(request.timeoutMs ?? DEFAULT_TIMEOUT_MS),
      });
    } catch (e) {
      const timedOut = e instanceof Error && e.name === "TimeoutError";
      throw new ApiError(timedOut ? "The TalNex API took too long to answer." : `Cannot reach the TalNex API at ${this.settings.apiUrl}.`,
        timedOut ? 504 : 503);
    }
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        if (response.ok) throw new ApiError("The TalNex API sent an answer that could not be read.", 502);
      }
    }
    if (!response.ok) throw new ApiError(errorMessage(data, response.status), response.status);
    return data as T;
  }
}

export function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && typeof (data as { error?: unknown }).error === "string") {
    return (data as { error: string }).error;
  }
  if (status === 401) return "The TalNex API did not accept the sign-in. Check AUTH_SECRET and TALNEX_EMAIL.";
  if (status === 403) return "This needs the other kind of account: check TALNEX_ROLE (organizer or recruiter).";
  if (status === 404) return "Not found (or it belongs to another account).";
  if (status >= 500) return `The TalNex API had a problem (error ${status}).`;
  return `The request was refused (error ${status}).`;
}
