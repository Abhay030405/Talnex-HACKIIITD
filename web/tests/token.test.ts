import { jwtVerify } from "jose";
import { describe, expect, it } from "vitest";

import { API_TOKEN_SECONDS, signApiToken } from "@/lib/token";

const SECRET = "0123456789abcdef0123";
const key = new TextEncoder().encode(SECRET);

// The same checks as backend/internal/auth/auth.go: HS256 only, an expiry is required, an email is required.
const verifyLikeTheApi = (token: string, currentDate?: Date) =>
  jwtVerify(token, key, { algorithms: ["HS256"], requiredClaims: ["exp", "email"], currentDate });

describe("API token", () => {
  it("passes the API's checks and carries email and name", async () => {
    const { payload, protectedHeader } = await verifyLikeTheApi(
      await signApiToken(SECRET, "person@example.com", "Person"),
    );
    expect(protectedHeader.alg).toBe("HS256");
    expect(payload.email).toBe("person@example.com");
    expect(payload.name).toBe("Person");
  });

  it("lives two minutes and no longer", async () => {
    const { payload } = await verifyLikeTheApi(await signApiToken(SECRET, "a@b.com"));
    expect((payload.exp ?? 0) - (payload.iat ?? 0)).toBe(API_TOKEN_SECONDS);
    const later = new Date(Date.now() + (API_TOKEN_SECONDS + 5) * 1000);
    await expect(verifyLikeTheApi(await signApiToken(SECRET, "a@b.com"), later)).rejects.toThrow();
  });

  it("writes the email the way the API stores it", async () => {
    const { payload } = await verifyLikeTheApi(await signApiToken(SECRET, "  Person@Example.COM "));
    expect(payload.email).toBe("person@example.com");
  });

  it("carries the sign-in door as a role only when there is one", async () => {
    expect((await verifyLikeTheApi(await signApiToken(SECRET, "a@b.com", "A", "recruiter"))).payload.role).toBe(
      "recruiter",
    );
    expect((await verifyLikeTheApi(await signApiToken(SECRET, "a@b.com", "A"))).payload.role).toBeUndefined();
  });

  it("refuses to sign what the API would refuse", async () => {
    await expect(signApiToken(SECRET, "  ")).rejects.toThrow(/email/);
    await expect(signApiToken(SECRET, "a@b.com", "A", "admin")).rejects.toThrow(/role/);
  });

  it("is rejected with another secret", async () => {
    const token = await signApiToken(SECRET, "person@example.com");
    await expect(jwtVerify(token, new TextEncoder().encode("another-secret-123456"))).rejects.toThrow();
  });
});
