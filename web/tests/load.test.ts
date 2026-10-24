import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import { problemText } from "@/lib/load";

describe("problems shown on a page", () => {
  it("tells a person on the wrong kind of account what to do", () => {
    const text = problemText(new ApiError("this page is for organizer accounts", 403), "your events");
    expect(text).toBe("this page is for organizer accounts. Sign out and use the other sign-in.");
  });

  it("says when something is missing or the server is away", () => {
    expect(problemText(new ApiError("not found", 404), "this event")).toBe("We could not find this event.");
    expect(problemText(new ApiError("Cannot reach the TalNex server.", 503), "your events")).toMatch(
      /Cannot reach the TalNex server\. Please try again/,
    );
  });

  it("never shows a raw error to the person", () => {
    expect(problemText(new Error("ECONNRESET at socket.js:12"), "your events")).toBe(
      "We could not load your events right now. Please try again in a moment.",
    );
  });
});
