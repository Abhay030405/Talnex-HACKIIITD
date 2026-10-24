import { afterEach, describe, expect, it, vi } from "vitest";

import { env } from "@/lib/env";

afterEach(() => vi.unstubAllEnvs());

describe("settings", () => {
  it("names a missing setting", () => {
    vi.stubEnv("API_BASE_URL", "");
    expect(() => env.apiBaseUrl).toThrow(/API_BASE_URL/);
  });

  it("trims the API address and checks it is a web address", () => {
    vi.stubEnv("API_BASE_URL", " http://api:8080/ ");
    expect(env.apiBaseUrl).toBe("http://api:8080");
    vi.stubEnv("API_BASE_URL", "api:8080");
    expect(() => env.apiBaseUrl).toThrow(/http/);
  });

  it("refuses a short shared secret, like the API does", () => {
    vi.stubEnv("AUTH_SECRET", "short");
    expect(() => env.authSecret).toThrow(/16/);
    vi.stubEnv("AUTH_SECRET", "0123456789abcdef");
    expect(env.authSecret).toBe("0123456789abcdef");
  });

  it("turns on email-only sign-in only when asked", () => {
    vi.stubEnv("ENABLE_DEV_LOGIN", "");
    expect(env.devLogin).toBe(false);
    vi.stubEnv("ENABLE_DEV_LOGIN", "true");
    expect(env.devLogin).toBe(true);
  });

  it("marks cookies secure only in production over https", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(env.secureCookies).toBe(false);
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("AUTH_URL", "https://talnex.example");
    expect(env.secureCookies).toBe(true);
    vi.stubEnv("AUTH_URL", "http://localhost:3000");
    expect(env.secureCookies).toBe(false);
  });
});
