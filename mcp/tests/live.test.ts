// Watching a check live: SSE parsing, replay then live, the time limit, reconnecting, and the digest of a real run.
import { readFileSync } from "node:fs";
import type { ServerResponse } from "node:http";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { foldLive, type LiveEvent, MAX_WATCH_SECONDS, parseSse, watchLive, watchSeconds } from "../src/live.js";
import { FakeApi } from "./fake-api.js";
import { apiFor, connect, EVENT, PROJECT } from "./helpers.js";

/** One run of the planted "honest" app (TinyTools), recorded from the local database's live_events. */
const REAL: LiveEvent[] = JSON.parse(readFileSync(new URL("./fixtures/live-sample.json", import.meta.url), "utf8"));
const REAL_ID = "b93b6f22-5c31-43db-bd4c-a41598568007";

/** Written exactly like backend/internal/http/live.go writes it. */
const frame = (ev: LiveEvent) => `event: ${ev.kind}\ndata: ${JSON.stringify(ev)}\n\n`;
const REPLAY_START = "event: replay.start\ndata: {}\n\n";
const REPLAY_DONE = "event: replay.done\ndata: {}\n\n";
const PING = ": ping\n\n";

const ev = (kind: string, more: Partial<LiveEvent> = {}): LiveEvent => ({ kind, subject: { kind: "project", id: "p1" }, data: {}, ...more });
const SMALL: LiveEvent[] = [
  ev("claims.queued", { data: { total: 2, claims: [{ id: "c1", text: "Add a todo" }, { id: "c2", text: "Share a list" }] } }),
  ev("stage.started", { stage: "live_test" }),
  ev("claim.started", { claim_id: "c1", data: { text: "Add a todo" } }),
  ev("step.record", { claim_id: "c1", data: { label: "Click Add" } }),
  ev("reason", { claim_id: "c1", data: { text: "The Add button is visible" } }),
  ev("run.finished", { data: { cost_usd: 0.0031 } }),
  ev("verdict", { claim_id: "c1", data: { verdict: "works", confidence: "high", reason: "seen" } }),
];
const SMALL_SSE = REPLAY_START + SMALL.map(frame).join("") + PING + REPLAY_DONE;

let fake: FakeApi;
beforeEach(async () => {
  fake = await new FakeApi().start();
});
afterEach(async () => fake.stop());

const openStream = (res: ServerResponse) => res.writeHead(200, { "Content-Type": "text/event-stream" });
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("parsing the stream", () => {
  it("gives the same events however the text is split into chunks", () => {
    const whole = parseSse(SMALL_SSE);
    expect(whole.rest).toBe("");
    expect(whole.events.map((e) => e.kind)).toEqual(["replay.start", ...SMALL.map((e) => e.kind)]); // ping and replay.done dropped
    for (let cut = 0; cut <= SMALL_SSE.length; cut++) {
      const first = parseSse(SMALL_SSE.slice(0, cut));
      const second = parseSse(first.rest + SMALL_SSE.slice(cut));
      expect([...first.events, ...second.events]).toEqual(whole.events);
    }
  });

  it("reads CRLF line endings and data split over several lines, and skips a broken event", () => {
    const text = 'event: reason\r\ndata: {"kind":"reason",\r\ndata: "subject":{"id":"p1"},"data":{"text":"hi"}}\r\n\r\n' +
                 "event: reason\ndata: {not json\n\n" + "event: verdict\n\n";
    expect(parseSse(text).events).toEqual([{ kind: "reason", subject: { id: "p1" }, data: { text: "hi" } }]);
  });

  it("names an event by its SSE name when the data has no kind", () => {
    expect(parseSse('event: reason\ndata: {"subject":{"id":"p1"}}\n\n').events).toEqual([{ kind: "reason", subject: { id: "p1" } }]);
  });
});

describe("folding events into a digest", () => {
  it("one digest per subject; a claim is never 'broken' before its verdict", () => {
    const [p1] = foldLive(SMALL);
    expect(p1.claims).toEqual({ c1: { text: "Add a todo", status: "works", confidence: "high", reason: "seen" },
                                c2: { text: "Share a list", status: "queued" } });
    expect(p1).toMatchObject({ actions: 1, browser_cost_usd: 0.0031, last_actions: ["Click Add"], last_reasons: ["The Add button is visible"],
                               stages: { live_test: "running" }, now: "live_test" });
  });

  it("stage endings: done, skipped, failed, retrying", () => {
    const [s] = foldLive([ev("stage.started", { stage: "a" }), ev("stage.finished", { stage: "a" }),
                          ev("stage.finished", { stage: "b", data: { skipped: true } }), ev("stage.failed", { stage: "c" }),
                          ev("stage.failed", { stage: "d", data: { status: "retrying" } }), { kind: "reason", data: {} }]);
    expect(s.stages).toEqual({ a: "done", b: "skipped", c: "failed", d: "retrying" });
    expect(s.now).toBe("");
  });

  it("keeps only the last five actions and reasons", () => {
    const many = Array.from({ length: 8 }, (_, i) => ev("step.record", { data: { label: `step ${i}` } }));
    expect(foldLive(many)[0].last_actions).toEqual(["step 3", "step 4", "step 5", "step 6", "step 7"]);
  });

  it("the recorded real run folds to what its events say", () => {
    const [s, ...others] = foldLive(REAL);
    expect(others).toHaveLength(0);
    expect(s).toMatchObject({ kind: "project", id: REAL_ID, now: "" });
    // every claim the run queued, each with the verdict the run gave it
    const queued = REAL.find((e) => e.kind === "claims.queued")!.data!.claims as { id: string; text: string }[];
    const verdicts = REAL.filter((e) => e.kind === "verdict");
    expect(Object.keys(s.claims).sort()).toEqual(queued.map((c) => c.id).sort());
    expect(queued).toHaveLength(7);
    for (const v of verdicts) expect(s.claims[v.claim_id!]).toMatchObject({ status: v.data!.verdict, confidence: v.data!.confidence });
    for (const c of queued) expect(s.claims[c.id].text).not.toBe("");
    // every stage that started also finished: done, or skipped when its finish event says so
    const finished = Object.fromEntries(REAL.filter((e) => e.kind === "stage.finished")
      .map((e) => [e.stage, e.data!.skipped === true ? "skipped" : "done"]));
    const started = new Set(REAL.filter((e) => e.kind === "stage.started").map((e) => e.stage));
    expect(Object.keys(finished).sort()).toEqual([...started].sort());
    expect(s.stages).toEqual(finished);
    expect(Object.values(s.stages)).toContain("done");
    // the counts and the cost add up
    expect(s.actions).toBe(REAL.filter((e) => e.kind === "step.record").length);
    const cost = REAL.filter((e) => e.kind === "run.finished").reduce((sum, e) => sum + Number(e.data!.cost_usd), 0);
    expect(s.browser_cost_usd).toBeCloseTo(cost, 6);
    expect(s.last_actions).toHaveLength(5);
    expect(s.last_reasons).toHaveLength(5);
  });
});

describe("watching", () => {
  it("replays the saved events, then keeps the live ones that arrive", async () => {
    fake.on("GET", `/v1/live/project/${PROJECT}`, (_req, res) => {
      openStream(res);
      res.write(REPLAY_START + SMALL.slice(0, 3).map(frame).join("") + REPLAY_DONE);
      setTimeout(() => res.write(SMALL.slice(3).map(frame).join("")), 300); // live, after the replay
    });
    const digest = await watchLive(apiFor(fake.url), "project", PROJECT, 1);
    expect(digest).toMatchObject({ events: 7, reconnects: 0 });
    expect(digest.subjects[0].claims.c1.status).toBe("works");
    expect(fake.seen[0].auth).toMatch(/^Bearer ey/);
  });

  it("the recorded real run, sent in odd-sized chunks, gives the same digest as folding it directly", async () => {
    const text = REPLAY_START + REAL.map(frame).join("") + REPLAY_DONE;
    fake.on("GET", `/v1/live/project/${REAL_ID}`, async (_req, res) => {
      openStream(res);
      for (let i = 0; i < text.length; i += 777) {
        res.write(text.slice(i, i + 777));
        if (i % (777 * 40) === 0) await wait(5);
      }
    });
    const digest = await watchLive(apiFor(fake.url), "project", REAL_ID, 2);
    expect(digest.events).toBe(REAL.length);
    expect(digest.subjects).toEqual(foldLive(REAL));
  });

  it("stops after the asked time even though the stream stays open", async () => {
    fake.on("GET", `/v1/live/event/${EVENT}`, (_req, res) => {
      openStream(res);
      res.write(PING);
    });
    const t0 = Date.now();
    const digest = await watchLive(apiFor(fake.url), "event", EVENT, 1);
    const took = Date.now() - t0;
    expect(took).toBeGreaterThanOrEqual(950);
    expect(took).toBeLessThan(2500);
    expect(digest).toMatchObject({ watched_seconds: 1, events: 0, reconnects: 0, subjects: [] });
  });

  it("never watches longer than 120 seconds or shorter than 1", () => {
    expect(MAX_WATCH_SECONDS).toBe(120);
    expect(watchSeconds(500)).toBe(120);
    expect(watchSeconds(120)).toBe(120);
    expect(watchSeconds(20)).toBe(20);
    expect(watchSeconds(0)).toBe(1);
    expect(watchSeconds(Number.NaN)).toBe(1);
  });

  it("the tool refuses more than 120 seconds before watching", async () => {
    const mcp = await connect(apiFor(fake.url));
    const out = await mcp.call("watch_live", { kind: "project", id: PROJECT, seconds: 121 });
    await mcp.close();
    expect(out.isError).toBe(true);
    expect(out.text).toContain("seconds");
    expect(fake.seen).toHaveLength(0);
  });

  it("reconnects when the stream drops, and the new replay does not count events twice", async () => {
    let connection = 0;
    fake.on("GET", `/v1/live/project/${PROJECT}`, (_req, res) => {
      connection += 1;
      openStream(res);
      if (connection === 1) {
        res.end(REPLAY_START + SMALL.slice(0, 2).map(frame).join("") + REPLAY_DONE); // drops early
      } else {
        res.write(REPLAY_START + SMALL.map(frame).join("") + REPLAY_DONE); // replays everything, stays open
      }
    });
    const digest = await watchLive(apiFor(fake.url), "project", PROJECT, 2);
    expect(digest.reconnects).toBe(1);
    expect(fake.seen).toHaveLength(2);
    expect(digest.events).toBe(SMALL.length);
    expect(digest.subjects).toEqual(foldLive(SMALL));
  });

  it("gives up reconnecting after five tries and keeps what it saw", async () => {
    fake.on("GET", `/v1/live/project/${PROJECT}`, (_req, res) => {
      openStream(res);
      res.end(REPLAY_START + frame(SMALL[1]));
    });
    const digest = await watchLive(apiFor(fake.url), "project", PROJECT, 30);
    expect(digest.reconnects).toBe(5);
    expect(fake.seen).toHaveLength(6);
    expect(digest.events).toBe(1);
  }, 10_000);

  it("a refused stream is an error with the API's words", async () => {
    fake.json("GET", `/v1/live/event/${EVENT}`, 404, { error: "not found" });
    await expect(watchLive(apiFor(fake.url), "event", EVENT, 1)).rejects.toThrow("not found");
    fake.on("GET", `/v1/live/event/${EVENT}`, (_req, res) => {
      res.writeHead(401);
      res.end();
    });
    await expect(watchLive(apiFor(fake.url), "event", EVENT, 1)).rejects.toThrow("Check AUTH_SECRET");
  });

  it("an API that is not running is an error, not an empty digest", async () => {
    const url = fake.url;
    await fake.stop();
    await expect(watchLive(apiFor(url), "project", PROJECT, 1)).rejects.toThrow(`Cannot reach the TalNex live stream at ${url}`);
  });
});
