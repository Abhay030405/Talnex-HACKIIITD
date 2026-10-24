// Our token must be exactly what the website sends, so the Go API cannot tell the two apart.
import { decodeProtectedHeader, jwtVerify } from "jose";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { signApiToken as websiteSign } from "@/lib/token";

import { signApiToken } from "../src/api.js";
import { SECRET } from "./helpers.js";

describe("the API token", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-24T12:00:00.500Z"));
  });
  afterEach(() => vi.useRealTimers());

  it.each([
    ["organizer@talnex.test", "organizer"],
    ["recruiter@talnex.test", "recruiter"],
    ["  Mixed.Case@TalNex.Test ", "organizer"],
  ])("is byte for byte the website's token for %s as %s", async (email, role) => {
    const ours = await signApiToken(SECRET, email, role);
    const website = await websiteSign(SECRET, email, "", role);
    expect(ours).toBe(website);
  });

  it("is HS256 with the email, an empty name, the role and a two-minute expiry", async () => {
    const token = await signApiToken(SECRET, " Organizer@Talnex.Test ", "organizer");
    expect(decodeProtectedHeader(token)).toEqual({ alg: "HS256", typ: "JWT" });
    const { payload } = await jwtVerify(token, new TextEncoder().encode(SECRET), { currentDate: new Date() });
    expect(payload).toEqual({ email: "organizer@talnex.test", name: "", role: "organizer",
                              iat: 1792843200, exp: 1792843200 + 120 });
  });

  it("is refused by a different secret", async () => {
    const token = await signApiToken(SECRET, "a@b.c", "organizer");
    await expect(jwtVerify(token, new TextEncoder().encode("another-secret"))).rejects.toThrow();
  });

  it("needs an email", async () => {
    await expect(signApiToken(SECRET, "   ", "organizer")).rejects.toThrow(/needs the person's email/);
  });
});
