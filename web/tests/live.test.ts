import { describe, expect, it } from "vitest";

import {
  claimWord,
  clock,
  emptyLiveState,
  isLiveKind,
  LOG_LIMIT,
  liveApiPath,
  reduceLive,
  tally,
  type LiveEvent,
  type LiveState,
} from "@/lib/live";
import { proxyLive, STREAM_HEADERS } from "@/lib/live-proxy";

const A = "11111111-1111-1111-1111-111111111111";
const B = "22222222-2222-2222-2222-222222222222";

const ev = (subject: string, extra: Partial<LiveEvent> = {}): LiveEvent => ({
  at: "2026-10-24T14:02:14.123Z",
  subject: { kind: "project", id: subject },
  ...extra,
});

function play(...steps: [string, LiveEvent][]): LiveState {
  return steps.reduce((s, [kind, e]) => reduceLive(s, kind, e), emptyLiveState());
}

describe("the live view state", () => {
  it("keeps each project apart, in the order they first appear", () => {
    const s = play(
      ["stage.started", ev(A, { stage: "live_test" })],
      ["stage.started", ev(B, { stage: "precheck" })],
      ["reason", ev(A, { data: { text: "click Add" } })],
    );
    expect(s.order).toEqual([A, B]);
    expect(s.subjects[A].current).toBe("testing the live site");
    expect(s.subjects[A].reason).toBe("click Add");
    expect(s.subjects[B].reason).toBe("");
    expect(s.subjects[B].log.map((l) => l.label)).toEqual(["precheck"]);
  });

  it("moves a claim from waiting to testing to its verdict, and never says broken before the verdict", () => {
    let s = play(["claims.queued", ev(A, { data: { total: 1, claims: [{ id: "c1", text: "Pin a note" }] } })]);
    expect(s.subjects[A].claims.c1.status).toBe("queued");
    s = reduceLive(s, "claim.started", ev(A, { claim_id: "c1", data: { text: "Pin a note" } }));
    expect(s.subjects[A].claims.c1.status).toBe("testing");
    s = reduceLive(s, "run.outcome", ev(A, { claim_id: "c1", data: { outcome: "broken" } }));
    s = reduceLive(s, "check", ev(A, { claim_id: "c1", data: { outcome: "broken", seen: "no pin" } }));
    expect(s.subjects[A].claims.c1.status).toBe("testing");
    s = reduceLive(s, "verdict", ev(A, { claim_id: "c1", data: { verdict: "broken", confidence: "medium", reason: "x" } }));
    expect(s.subjects[A].claims.c1).toMatchObject({ status: "broken", confidence: "medium", reason: "x" });
    expect(s.verdicts).toBe(1);
    expect(tally(s.subjects[A])).toMatchObject({ total: 1, broken: 1, testing: 0 });
    expect(claimWord("partly_works")).toBe("partly works");
  });

  it("ignores a verdict it does not know", () => {
    const s = play(["verdict", ev(A, { claim_id: "c1", data: { verdict: "maybe" } })]);
    expect(s).toEqual(emptyLiveState());
  });

  it("shows the latest screen with where it clicked, and counts actions and browser cost", () => {
    const s = play(
      ["step.record", ev(A, { data: { label: "Click Add", proof_url: "https://files.test/a.jpg", box: { x: 10, y: 20, w: 30, h: 40 } } })],
      ["step.record", ev(A, { data: { label: "Type", proof_url: "javascript:alert(1)" } })],
      ["run.finished", ev(A, { data: { outcome: "works", cost_usd: 0.0021 } })],
      ["run.finished", ev(B, { data: { outcome: "works", cost_usd: 0.001 } })],
    );
    expect(s.subjects[A].shot).toEqual({ url: "https://files.test/a.jpg", box: { x: 10, y: 20, w: 30, h: 40 } });
    expect(s.subjects[A].label).toBe("Type");
    expect(s.actions).toBe(2);
    expect(s.costUsd).toBeCloseTo(0.0031);
  });

  it("tracks stages, keeps the log short, and skips events with no subject", () => {
    let s = play(
      ["stage.started", ev(A, { stage: "claims" })],
      ["stage.finished", ev(A, { stage: "claims", data: { skipped: true, reason: "no video" } })],
      ["stage.failed", ev(A, { stage: "live_test", data: { status: "retrying", error: "timeout" } })],
    );
    expect(s.subjects[A].stages).toEqual([["claims", "skipped"], ["live_test", "retrying"]]);
    for (let i = 0; i < LOG_LIMIT + 20; i++) s = reduceLive(s, "reason", ev(A, { data: { text: `r${i}` } }));
    expect(s.subjects[A].log).toHaveLength(LOG_LIMIT);
    expect(reduceLive(s, "reason", { data: { text: "x" } })).toBe(s);
    expect(reduceLive(s, "unknown.kind", ev(A))).toBe(s);
  });

  it("knows the four kinds and builds the API path", () => {
    expect(["project", "candidate_project", "candidate", "event"].every(isLiveKind)).toBe(true);
    expect(isLiveKind("planet")).toBe(false);
    expect(liveApiPath("event", "a/b")).toBe("/v1/live/event/a%2Fb");
    expect(clock("not a date")).toBe("");
  });
});

describe("the stream proxy", () => {
  const caller = { email: "org@talnex.test", name: "Org", role: "organizer" };
  const deps = (respond: (url: string, init?: RequestInit) => Promise<Response>) => ({
    baseUrl: "http://api.test",
    secret: "a-test-secret-of-enough-length",
    fetch: respond as unknown as typeof fetch,
  });

  it("opens the API stream with a signed token and passes it straight through", async () => {
    let seen: { url: string; auth: string } | null = null;
    const res = await proxyLive("project", A, caller, new AbortController().signal, deps(async (url, init) => {
      seen = { url, auth: String((init?.headers as Record<string, string>).Authorization) };
      return new Response("event: replay.start\ndata: {}\n\n", { status: 200 });
    }));
    expect(seen).toMatchObject({ url: `http://api.test/v1/live/project/${A}` });
    expect(seen!.auth).toMatch(/^Bearer ey/);
    expect(res.headers.get("Content-Type")).toBe(STREAM_HEADERS["Content-Type"]);
    expect(await res.text()).toContain("replay.start");
  });

  it("turns refusals into plain words and never leaks the API's body", async () => {
    const refuse = (status: number) => deps(async () => new Response("internal details", { status }));
    expect((await proxyLive("event", A, caller, new AbortController().signal, refuse(404))).status).toBe(404);
    const off = await proxyLive("event", A, caller, new AbortController().signal, refuse(503));
    expect(await off.json()).toEqual({ error: "The live view is off on this server." });
    const down = await proxyLive("event", A, caller, new AbortController().signal, deps(async () => {
      throw new Error("ECONNREFUSED");
    }));
    expect(down.status).toBe(503);
  });
});

describe("log lines name their claim", () => {
  it("numbers each line by the claim it belongs to, in the order claims appeared", async () => {
    const { reduceLive, emptyLiveState } = await import("@/lib/live");
    const subject = { kind: "project", id: "p1" };
    let s = reduceLive(emptyLiveState(), "claims.queued", {
      kind: "claims.queued", subject, data: { total: 2, claims: [{ id: "a", text: "Add todos" }, { id: "b", text: "Tick todos" }] },
    });
    s = reduceLive(s, "reason", { kind: "reason", subject, claim_id: "b", data: { text: "click the box" } });
    s = reduceLive(s, "stage.started", { kind: "stage.started", subject, stage: "live_test", data: {} });
    const log = s.subjects.p1.log;
    expect(log[log.length - 2].claim).toBe("#2");
    expect(log[log.length - 1].claim).toBeUndefined();
  });
});

describe("panel status", () => {
  it("says finished once the last stage ended, waiting between stages, and what runs now", async () => {
    const { reduceLive, emptyLiveState, panelStatus } = await import("@/lib/live");
    const subject = { kind: "project", id: "p1" };
    let s = reduceLive(emptyLiveState(), "stage.started", { kind: "stage.started", subject, stage: "live_test", data: {} });
    expect(panelStatus(s.subjects.p1)).not.toBe("");
    s = reduceLive(s, "stage.finished", { kind: "stage.finished", subject, stage: "live_test", data: {} });
    expect(panelStatus(s.subjects.p1)).toBe("waiting");
    s = reduceLive(s, "stage.started", { kind: "stage.started", subject, stage: "project_report", data: {} });
    s = reduceLive(s, "stage.finished", { kind: "stage.finished", subject, stage: "project_report", data: {} });
    expect(panelStatus(s.subjects.p1)).toBe("finished");
  });
});
