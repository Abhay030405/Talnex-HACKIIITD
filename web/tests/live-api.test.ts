import { describe, expect, it } from "vitest";

import { callApi, type ApiDeps } from "@/lib/api";

// Checks the website's token and API client against a running Go API. Skipped unless both are set:
//   LIVE_API_URL=http://localhost:8080 LIVE_AUTH_SECRET=<AUTH_SECRET from .env> npm test -- live-api
// It signs in as two test accounts (one per role) on that API, which creates them if they do not exist.
const baseUrl = process.env.LIVE_API_URL ?? "";
const secret = process.env.LIVE_AUTH_SECRET ?? "";
const live = baseUrl && secret ? describe : describe.skip;

live("the website against a running API", () => {
  const deps: ApiDeps = { baseUrl, secret, fetch };
  const organizer = { email: "live-check-organizer@talnex.test", name: "Live check", role: "organizer" };
  const recruiter = { email: "live-check-recruiter@talnex.test", name: "Live check", role: "recruiter" };

  it("is let in with its token, each role to its own list", async () => {
    expect(Array.isArray(await callApi(organizer, "/v1/events", {}, deps))).toBe(true);
    expect(Array.isArray(await callApi(recruiter, "/v1/candidates", {}, deps))).toBe(true);
  });

  it("is kept out of the other role's list", async () => {
    await expect(callApi(recruiter, "/v1/events", {}, deps)).rejects.toMatchObject({ status: 403 });
  });

  it("cannot switch an account to the other role", async () => {
    await expect(callApi({ ...recruiter, role: "organizer" }, "/v1/events", {}, deps)).rejects.toMatchObject({
      status: 403,
      message: expect.stringMatching(/already has a recruiter account/),
    });
  });

  it("is refused with another secret", async () => {
    await expect(
      callApi(organizer, "/v1/events", {}, { ...deps, secret: "not-the-real-secret-123" }),
    ).rejects.toMatchObject({ status: 401 });
  });
});
