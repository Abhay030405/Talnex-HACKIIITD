// The one place this server reads its settings. A missing one stops it with a message naming the setting.

export type Role = "organizer" | "recruiter";

export interface Settings {
  apiUrl: string;
  secret: string;
  email: string;
  role: Role;
}

export class SettingsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SettingsError";
  }
}

export function loadSettings(env: Record<string, string | undefined> = process.env): Settings {
  const missing = ["TALNEX_API_URL", "AUTH_SECRET", "TALNEX_EMAIL", "TALNEX_ROLE"].filter((k) => !env[k]?.trim());
  if (missing.length) {
    throw new SettingsError(`Missing setting${missing.length > 1 ? "s" : ""}: ${missing.join(", ")} (see mcp/README.md)`);
  }
  const role = env.TALNEX_ROLE!.trim().toLowerCase();
  if (role !== "organizer" && role !== "recruiter") {
    throw new SettingsError(`TALNEX_ROLE must be "organizer" or "recruiter", not "${env.TALNEX_ROLE}"`);
  }
  const apiUrl = env.TALNEX_API_URL!.trim().replace(/\/+$/, "");
  if (!/^https?:\/\//.test(apiUrl)) throw new SettingsError(`TALNEX_API_URL must start with http:// or https://`);
  return { apiUrl, secret: env.AUTH_SECRET!.trim(), email: env.TALNEX_EMAIL!.trim().toLowerCase(), role };
}
