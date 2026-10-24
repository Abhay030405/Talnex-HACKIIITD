import { describe, expect, it } from "vitest";

import { GET } from "@/app/healthz/route";

describe("/healthz", () => {
  it("answers ok as JSON, as the Compose health check expects", async () => {
    const res = GET();
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual({ status: "ok" });
  });
});
