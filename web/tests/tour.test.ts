import { beforeEach, describe, expect, it, vi } from "vitest";

import { isFocusPage } from "@/components/ui/ShellFrame";
import { ApiError } from "@/lib/api";
import {
  MAX_TOUR_QUESTION_CHARS,
  TOUR_EVENT_KINDS,
  cleanTourQuestion,
  codeLabel,
  emptyTourLive,
  isTourId,
  reduceTour,
  tourMessagesPath,
  tourPageUrl,
  tourPath,
  tourStartPath,
  workingWords,
  type TourEvent,
  type TourLive,
} from "@/lib/tour";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api", async (real) => ({ ...(await real<typeof import("@/lib/api")>()), apiFetch }));

const start = await import("@/app/api/tours/route");
const one = await import("@/app/api/tours/[tourId]/route");

const TOUR = "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d";
const MSG = "11111111-2222-4333-8444-555555555555";

beforeEach(() => apiFetch.mockReset());

const ev = (data: Record<string, unknown> = {}, extra: Partial<TourEvent> = {}): TourEvent => ({
  tour_id: TOUR,
  message_id: MSG,
  data,
  ...extra,
});
const fold = (events: [string, TourEvent][], from: TourLive = emptyTourLive()) =>
  events.reduce((state, [kind, event]) => reduceTour(state, kind, event, TOUR), from);

describe("tour paths", () => {
  it("builds the API paths and the page address for both kinds of project", () => {
    expect(tourStartPath("project", "p 1")).toBe("/v1/projects/p%201/tours");
    expect(tourStartPath("candidate_project", "c1")).toBe("/v1/candidate-projects/c1/tours");
    expect(tourPath(TOUR)).toBe(`/v1/tours/${TOUR}`);
    expect(tourMessagesPath(TOUR)).toBe(`/v1/tours/${TOUR}/messages`);
    expect(tourPageUrl("project", "p1", "e1")).toBe("/events/e1/projects/p1/walkthrough");
    expect(tourPageUrl("candidate_project", "c1", "k1", TOUR)).toBe(`/candidates/k1/projects/c1/walkthrough?tour=${TOUR}`);
  });

  it("only accepts a real-looking tour id and a question within the API's limit", () => {
    expect(isTourId(TOUR)).toBe(true);
    expect(isTourId("../x")).toBe(false);
    expect(isTourId(undefined)).toBe(false);
    expect(cleanTourQuestion("  How is login done?  ")).toBe("How is login done?");
    expect(cleanTourQuestion("x".repeat(MAX_TOUR_QUESTION_CHARS + 9))).toHaveLength(MAX_TOUR_QUESTION_CHARS);
    expect(cleanTourQuestion(7)).toBe("");
  });

  it("names a piece of code by its file and lines", () => {
    expect(codeLabel({ kind: "code", file: "src/app.js", start: 2, end: 9 })).toBe("src/app.js, lines 2 to 9");
    expect(codeLabel({ kind: "code", file: "src/app.js", start: 4, end: 4 })).toBe("src/app.js, line 4");
    expect(codeLabel({ kind: "code", file: "src/app.js" })).toBe("src/app.js");
  });
});

describe("the full-width frame", () => {
  it("hides the sidebar only on a walk-through page", () => {
    expect(isFocusPage("/events/e1/projects/p1/walkthrough")).toBe(true);
    expect(isFocusPage("/candidates/c1/projects/p1/walkthrough")).toBe(true);
    expect(isFocusPage("/events/e1/projects/p1")).toBe(false);
    expect(isFocusPage("/events/e1/projects/p1/live")).toBe(false);
    expect(isFocusPage("/events/walkthroughs")).toBe(false);
  });
});

describe("the live part of a chat", () => {
  it("shows what the guide reads, says and shows, in order", () => {
    const state = fold([
      ["tour.started", ev({ question: "How are items added?" })],
      ["tour.status", ev({ text: "Reading the code" })],
      ["tour.read", ev({ tool: "search", what: '"addItem"' })],
      ["tour.say", ev({ index: 1, total: 2, text: "Items are added in addItem.", proof: [{ file: "src/app.js", start: 2, end: 5, url: "https://github.com/o/r/blob/x/src/app.js#L2-L5" }] })],
      ["tour.code", ev({ index: 1, snippets: [{ file: "src/app.js", start: 2, end: 5, lines: ["function addItem(text) {"] }] })],
      ["step.record", ev({ proof_url: "https://files.example/view/shot", label: 'Click "Add"', url: "https://demo.example.com/", box: { x: 10, y: 20, w: 30, h: 40 } })],
    ]);
    expect(state.messageId).toBe(MSG);
    expect(state.reads).toEqual(['search "addItem"']);
    expect(state.says).toHaveLength(1);
    expect(state.says[0].snippets[0].lines).toEqual(["function addItem(text) {"]);
    expect(state.shot).toEqual({ url: "https://files.example/view/shot", box: { x: 10, y: 20, w: 30, h: 40 }, label: 'Click "Add"', page: "https://demo.example.com/" });
    expect(workingWords(state)).toBe("Thinking…");   // nothing new to report, but not finished yet
    expect(workingWords(fold([["tour.status", ev({ text: "Reading the code" })]]))).toBe("Reading the code");
  });

  it("ignores the events of other tours and kinds it does not know", () => {
    const other = ev({ index: 1, text: "Someone else's tour" }, { tour_id: "99999999-9999-4999-8999-999999999999" });
    expect(fold([["tour.say", other], ["something.else", ev()]])).toEqual(emptyTourLive());
  });

  it("does not say a sentence twice when a replay repeats it", () => {
    const say = ev({ index: 1, text: "Once." });
    expect(fold([["tour.say", say], ["tour.say", say]]).says).toHaveLength(1);
  });

  it("puts a note on its step, and a note for the whole tour on the chat", () => {
    const state = fold([
      ["tour.say", ev({ index: 1, text: "Step one." })],
      ["tour.notice", ev({ index: 1, text: "I couldn't show this on the live site." })],
      ["tour.notice", ev({ text: "This project has no live link." })],
      ["tour.notice", ev({ text: "This project has no live link." })],
    ]);
    expect(state.says[0].note).toBe("I couldn't show this on the live site.");
    expect(state.notices).toEqual(["This project has no live link."]);
  });

  it("starts the live part again for a new question but keeps the last picture", () => {
    const first = fold([
      ["tour.say", ev({ index: 1, text: "First answer." })],
      ["step.record", ev({ proof_url: "https://files.example/view/one" })],
      ["tour.done", ev({ status: "done" })],
    ]);
    expect(first.finished).toBe("done");
    const second = reduceTour(first, "tour.started", ev({}, { message_id: "22222222-3333-4444-8555-666666666666" }), TOUR);
    expect(second.says).toEqual([]);
    expect(second.finished).toBeNull();
    expect(second.shot?.url).toBe("https://files.example/view/one");
  });

  it("keeps only the box that is a real rectangle, and skips pictures with no link", () => {
    const bad = fold([["step.record", ev({ proof_url: "https://files.example/view/x", box: { x: 1, y: 2, w: 0, h: 5 } })]]);
    expect(bad.shot?.box).toBeNull();
    expect(fold([["step.record", ev({ label: "no picture" })]]).shot).toBeNull();
  });

  it("shows a failure as finished, and lists every kind the page listens for", () => {
    expect(fold([["tour.done", ev({ status: "failed" })]]).finished).toBe("failed");
    expect(TOUR_EVENT_KINDS).toContain("step.record");
    expect(TOUR_EVENT_KINDS).toContain("tour.say");
  });
});

describe("the tour routes", () => {
  it("starts a chat for a project and passes the API's answer on", async () => {
    apiFetch.mockResolvedValue({ id: TOUR, message_id: MSG, status: "queued" });
    const response = await start.POST(
      new Request("http://x/api/tours", { method: "POST", body: JSON.stringify({ subject: "project", id: "p1", question: "  How?  " }) }),
    );
    expect(response.status).toBe(202);
    expect(apiFetch).toHaveBeenCalledWith("/v1/projects/p1/tours", { method: "POST", body: { question: "How?" } });
  });

  it("refuses an unknown kind of project and an empty question before calling the API", async () => {
    const post = (body: unknown) => start.POST(new Request("http://x/api/tours", { method: "POST", body: JSON.stringify(body) }));
    expect((await post({ subject: "candidate", id: "c", question: "q" })).status).toBe(400);
    expect((await post({ subject: "project", id: "p", question: "   " })).status).toBe(400);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("reads a chat and adds a question to it, and never calls the API with a strange id", async () => {
    apiFetch.mockResolvedValue({ id: TOUR, subject: { kind: "project", id: "p" }, messages: [] });
    const params = (tourId: string) => ({ params: Promise.resolve({ tourId }) });
    expect((await one.GET(new Request("http://x"), params(TOUR))).status).toBe(200);
    expect(apiFetch).toHaveBeenCalledWith(`/v1/tours/${TOUR}`);
    expect((await one.GET(new Request("http://x"), params("../etc"))).status).toBe(404);
    apiFetch.mockClear();
    await one.POST(new Request("http://x", { method: "POST", body: JSON.stringify({ question: "And login?" }) }), params(TOUR));
    expect(apiFetch).toHaveBeenCalledWith(`/v1/tours/${TOUR}/messages`, { method: "POST", body: { question: "And login?" } });
    expect((await one.POST(new Request("http://x", { method: "POST", body: "{}" }), params(TOUR))).status).toBe(400);
  });

  it("turns the API's refusal into plain words with its status", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("the daily limit of tours for this project is reached; try again tomorrow", 429));
    const response = await start.POST(
      new Request("http://x/api/tours", { method: "POST", body: JSON.stringify({ subject: "project", id: "p1", question: "q" }) }),
    );
    expect(response.status).toBe(429);
    expect(await response.json()).toEqual({ error: "the daily limit of tours for this project is reached; try again tomorrow" });
  });
});
