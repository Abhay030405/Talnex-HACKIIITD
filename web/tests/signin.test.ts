import { describe, expect, it } from "vitest";

import type { ApiDeps } from "@/lib/api";
import { checkDoor, checkPassword, cleanEmail, passwordProblem, registerPassword, signInError } from "@/lib/signin";

const SECRET = "0123456789abcdef0123";

function api(answer: () => Response | Promise<Response>) {
  const calls: string[] = [];
  const deps: ApiDeps = {
    baseUrl: "http://api:8080",
    secret: SECRET,
    fetch: (async (url: string) => {
      calls.push(url);
      return answer();
    }) as unknown as typeof fetch,
  };
  return { deps, calls };
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const person = { email: "a@example.com", name: "A" };

describe("cleanEmail", () => {
  it("cleans a real email the way the API stores it", () => {
    expect(cleanEmail("  Person@Example.COM ")).toBe("person@example.com");
  });

  it.each([["not-an-email"], ["a@b"], [""], [undefined], ["a b@c.com"], [`${"x".repeat(250)}@example.com`]])(
    "refuses %p",
    (value) => {
      expect(cleanEmail(value)).toBeNull();
    },
  );
});

describe("checkDoor", () => {
  it("lets the person in when the API accepts this door", async () => {
    const { deps, calls } = api(() => json(200, { id: "u1", email: "a@example.com" }));
    expect(await checkDoor(person, "recruiter", deps)).toBe("ok");
    expect(calls).toEqual(["http://api:8080/v1/me"]);
  });

  it("sends the person back when the email belongs to the other role", async () => {
    const { deps } = api(() => json(403, { error: "this email already has a organizer account" }));
    expect(await checkDoor(person, "recruiter", deps)).toBe("wrong-door");
  });

  it("lets the person in when the API cannot answer, so the workspace can show why", async () => {
    expect(await checkDoor(person, "recruiter", api(() => json(500, { error: "boom" })).deps)).toBe("ok");
    expect(await checkDoor(person, "recruiter", api(() => Promise.reject(new TypeError("down"))).deps)).toBe("ok");
  });

  it("asks nothing when the door was forgotten on the way", async () => {
    const { deps, calls } = api(() => json(200, {}));
    expect(await checkDoor(person, undefined, deps)).toBe("no-door");
    expect(calls).toEqual([]);
  });
});

describe("signInError", () => {
  it("says nothing without an error", () => {
    expect(signInError(undefined)).toBeNull();
  });

  it("points to the other door", () => {
    expect(signInError("wrong-door", "recruiter")).toMatch(/hackathon organizer account.*organizer sign-in/);
    expect(signInError("wrong-door", "organizer")).toMatch(/recruiter account.*recruiter sign-in/);
  });

  it("explains each known problem in words", () => {
    for (const code of ["no-door", "unverified", "AccessDenied", "Configuration", "failed", "SomethingNew"]) {
      expect(signInError(code)?.length).toBeGreaterThan(10);
    }
  });
});

describe("passwords", () => {
  it("uses the API's length rule and checks the second copy", () => {
    expect(passwordProblem("short")).toMatch(/8 to 128/);
    expect(passwordProblem("x".repeat(129))).toMatch(/8 to 128/);
    expect(passwordProblem("long enough")).toBeNull();
    expect(passwordProblem("long enough", "long enougj")).toMatch(/do not match/);
  });

  it("returns the account for a right password and null for a wrong one or too many tries", async () => {
    const ok = api(() => json(200, { email: "a@example.com", name: "A", role: "recruiter" }));
    expect(await checkPassword("a@example.com", "pw", "1.2.3.4", ok.deps)).toEqual({
      email: "a@example.com", name: "A", role: "recruiter",
    });
    expect(ok.calls[0]).toBe("http://api:8080/v1/auth/password-login");
    for (const status of [401, 429]) {
      const { deps } = api(() => json(status, { error: "email or password is wrong" }));
      expect(await checkPassword("a@example.com", "pw", "", deps)).toBeNull();
    }
  });

  it("shows the API's reason when it refuses a registration", async () => {
    const { deps } = api(() => json(409, { error: "this email already has an account; sign in instead" }));
    await expect(registerPassword(person, "recruiter", "long enough", "", deps)).rejects.toThrow(/sign in instead/);
  });
});
