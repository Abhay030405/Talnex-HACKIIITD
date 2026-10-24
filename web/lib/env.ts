// The one place in the website that reads environment settings (AGENTS.md section 5).
// Values are read when first used, not when the file loads, so `next build` works without any secrets.
// Nothing here reaches the browser.
import "server-only";

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required setting ${name} (see .env.example)`);
  return value;
}

function optional(name: string): string {
  return process.env[name]?.trim() ?? "";
}

export const MIN_SECRET_LENGTH = 16;

export const env = {
  /** Address the website server uses to reach the Go API, for example http://api:8080. */
  get apiBaseUrl(): string {
    const value = required("API_BASE_URL").replace(/\/+$/, "");
    if (!/^https?:\/\/[^\s/]+/.test(value)) throw new Error("API_BASE_URL must start with http:// or https://");
    return value;
  },
  /** Shared with the Go API: signs the short-lived token that tells the API who is calling. */
  get authSecret(): string {
    const secret = required("AUTH_SECRET");
    if (secret.length < MIN_SECRET_LENGTH) {
      throw new Error(`AUTH_SECRET must be at least ${MIN_SECRET_LENGTH} characters`);
    }
    return secret;
  },
  /** Google sign-in is offered only when both are set. */
  get googleClientId(): string {
    return optional("GOOGLE_CLIENT_ID");
  },
  get googleClientSecret(): string {
    return optional("GOOGLE_CLIENT_SECRET");
  },
  /** Email-only sign-in for local work. Keep false in production. */
  get devLogin(): boolean {
    return optional("ENABLE_DEV_LOGIN") === "true";
  },
  /** Address shown on the contact page. Empty hides it. */
  get contactEmail(): string {
    return optional("CONTACT_EMAIL");
  },
  /** Docs API playground: the API addresses a browser may name (TALNEX_DOCS_API_ORIGINS, comma separated). The
   *  playground proxy sends them on to API_BASE_URL, so they work from inside Docker too. */
  get docsApiOrigins(): string[] {
    return (optional("TALNEX_DOCS_API_ORIGINS") || "http://localhost:8080")
      .split(",")
      .map((o) => o.trim().replace(/\/+$/, ""))
      .filter(Boolean);
  },
  /** Docs "Get a test token" helper, local testing only. Off unless TALNEX_DOCS_DEV_TOKENS=true. */
  get docsDevTokens(): boolean {
    return optional("TALNEX_DOCS_DEV_TOKENS") === "true";
  },
  /** How long a docs test token lasts, in minutes (at most a day). */
  get docsDevTokenMinutes(): number {
    const minutes = Number(optional("TALNEX_DOCS_DEV_TOKEN_MINUTES") || "30");
    return Number.isFinite(minutes) && minutes > 0 ? Math.min(minutes, 24 * 60) : 30;
  },
  /** Cookies are marked secure (https only) outside local development. */
  get secureCookies(): boolean {
    return optional("NODE_ENV") === "production" && !optional("AUTH_URL").startsWith("http://");
  },
};
