import { jwtVerify } from "jose";
import { describe, expect, it } from "vitest";

import { ApiError, callApi, type ApiDeps } from "@/lib/api";

const SECRET = "0123456789abcdef0123";
const caller = { email: "rec@example.com", name: "Rec", role: "recruiter" };

type Seen = { url: string; init: RequestInit };

function fakeApi(answer: () => Response | Promise<Response>) {
  const seen: Seen[] = [];
  const deps: ApiDeps = {
    baseUrl: "http://api:8080",
    secret: SECRET,
    fetch: (async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return answer();
    }) as unknown as typeof fetch,
  };
  return { deps, seen };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("callApi", () => {
  it("GETs with a valid token for the caller and returns the JSON", async () => {
    const { deps, seen } = fakeApi(() => json(200, [{ id: "e1" }]));
    expect(await callApi(caller, "/v1/events", {}, deps)).toEqual([{ id: "e1" }]);
    expect(seen[0].url).toBe("http://api:8080/v1/events");
    expect(seen[0].init.method).toBe("GET");
    expect(seen[0].init.cache).toBe("no-store");
    const headers = seen[0].init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
    const token = headers.Authorization.replace(/^Bearer /, "");
    const { payload } = await jwtVerify(token, new TextEncoder().encode(SECRET));
    expect(payload).toMatchObject({ email: "rec@example.com", name: "Rec", role: "recruiter" });
  });

  it("POSTs a body as JSON", async () => {
    const { deps, seen } = fakeApi(() => json(201, { id: "c1" }));
    await callApi(caller, "/v1/candidates", { body: { label: "A" } }, deps);
    expect(seen[0].init.method).toBe("POST");
    expect((seen[0].init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(seen[0].init.body).toBe('{"label":"A"}');
  });

  it("sends a form as is, leaving its content type to fetch", async () => {
    const { deps, seen } = fakeApi(() => json(202, { ok: true }));
    const form = new FormData();
    form.set("label", "A");
    await callApi(caller, "/v1/candidates/resume", { form }, deps);
    expect(seen[0].init.body).toBe(form);
    expect((seen[0].init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("returns null for an empty answer", async () => {
    const { deps } = fakeApi(() => new Response(null, { status: 204 }));
    expect(await callApi(caller, "/v1/x", { method: "DELETE" }, deps)).toBeNull();
  });

  it("passes the API's own error words through", async () => {
    const { deps } = fakeApi(() => json(403, { error: "this email already has a organizer account" }));
    const err = await callApi(caller, "/v1/candidates", {}, deps).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 403, message: "this email already has a organizer account" });
  });

  it("turns a non-JSON error page into plain words", async () => {
    const { deps } = fakeApi(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(callApi(caller, "/v1/x", {}, deps)).rejects.toMatchObject({
      status: 502,
      message: expect.stringMatching(/server had a problem/),
    });
  });

  it("says when the server cannot be reached or is too slow", async () => {
    const down = fakeApi(() => Promise.reject(new TypeError("fetch failed")));
    await expect(callApi(caller, "/v1/x", {}, down.deps)).rejects.toMatchObject({ status: 503 });
    const slow = fakeApi(() => Promise.reject(Object.assign(new Error("timed out"), { name: "TimeoutError" })));
    await expect(callApi(caller, "/v1/x", {}, slow.deps)).rejects.toMatchObject({ status: 504 });
  });

  it("refuses a path without a leading slash", async () => {
    const { deps } = fakeApi(() => json(200, {}));
    await expect(callApi(caller, "v1/x", {}, deps)).rejects.toThrow(/start with/);
  });
});
