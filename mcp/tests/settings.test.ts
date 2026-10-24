import { describe, expect, it } from "vitest";

import { loadSettings, SettingsError } from "../src/settings.js";

const FULL = { TALNEX_API_URL: "http://localhost:8080", AUTH_SECRET: "s", TALNEX_EMAIL: "a@b.c", TALNEX_ROLE: "organizer" };

describe("settings", () => {
  it.each(Object.keys(FULL))("stops with the name of a missing %s", (name) => {
    const env: Record<string, string> = { ...FULL };
    delete env[name];
    expect(() => loadSettings(env)).toThrow(SettingsError);
    expect(() => loadSettings(env)).toThrow(new RegExp(`Missing setting: ${name} `));
  });

  it("treats a blank value as missing", () => {
    expect(() => loadSettings({ ...FULL, AUTH_SECRET: "   " })).toThrow(/Missing setting: AUTH_SECRET/);
  });

  it("names every missing setting at once", () => {
    expect(() => loadSettings({})).toThrow("Missing settings: TALNEX_API_URL, AUTH_SECRET, TALNEX_EMAIL, TALNEX_ROLE");
  });

  it("refuses an unknown role and an address without http", () => {
    expect(() => loadSettings({ ...FULL, TALNEX_ROLE: "admin" })).toThrow(/TALNEX_ROLE must be "organizer" or "recruiter"/);
    expect(() => loadSettings({ ...FULL, TALNEX_API_URL: "localhost:8080" })).toThrow(/TALNEX_API_URL must start with http/);
  });

  it("tidies the values", () => {
    const s = loadSettings({ TALNEX_API_URL: " http://localhost:8080/ ", AUTH_SECRET: " s ", TALNEX_EMAIL: " A@B.C ", TALNEX_ROLE: "Recruiter" });
    expect(s).toEqual({ apiUrl: "http://localhost:8080", secret: "s", email: "a@b.c", role: "recruiter" });
  });
});
