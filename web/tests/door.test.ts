import { beforeEach, describe, expect, it, vi } from "vitest";

const jar = new Map<string, { value: string; options: Record<string, unknown> }>();

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (jar.has(name) ? { name, value: jar.get(name)!.value } : undefined),
    set: (name: string, value: string, options: Record<string, unknown>) => jar.set(name, { value, options }),
    delete: (name: string) => jar.delete(name),
  }),
}));

const { DOOR_COOKIE, DOOR_SECONDS, forgetDoor, recallDoor, rememberDoor } = await import("@/lib/door");

beforeEach(() => jar.clear());

describe("sign-in door", () => {
  it("remembers the door in a short-lived cookie the page scripts cannot read", async () => {
    await rememberDoor("organizer");
    expect(jar.get(DOOR_COOKIE)).toMatchObject({
      value: "organizer",
      options: { httpOnly: true, sameSite: "lax", path: "/", maxAge: DOOR_SECONDS },
    });
    expect(await recallDoor()).toBe("organizer");
  });

  it("ignores a cookie that is not a real role", async () => {
    jar.set(DOOR_COOKIE, { value: "admin", options: {} });
    expect(await recallDoor()).toBeUndefined();
  });

  it("forgets the door", async () => {
    await rememberDoor("recruiter");
    await forgetDoor();
    expect(await recallDoor()).toBeUndefined();
  });
});
