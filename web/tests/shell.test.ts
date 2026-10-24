import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const { isActive } = await import("@/components/ui/ShellNav");

const events = { href: "/organizer", label: "Events", icon: "calendar" as const, also: ["/events"] };
const create = { href: "/new/hackathon", label: "New event", icon: "plus" as const };

describe("workspace links", () => {
  it("light up on their own page and the pages under them", () => {
    expect(isActive("/organizer", events)).toBe(true);
    expect(isActive("/events/e1", events)).toBe(true);
    expect(isActive("/events/e1/compare", events)).toBe(true);
    expect(isActive("/new/hackathon", create)).toBe(true);
  });

  it("do not light up for a page that only starts with the same letters", () => {
    expect(isActive("/eventsx", events)).toBe(false);
    expect(isActive("/organizers", events)).toBe(false);
    expect(isActive("/new/hackathon", events)).toBe(false);
  });
});
