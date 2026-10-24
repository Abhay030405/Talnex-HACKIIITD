import { describe, expect, it } from "vitest";

import config, { FORM_BODY_LIMIT } from "@/next.config";
import pkg from "@/package.json";

const megabytes = (size: string) => Number(/^(\d+)mb$/i.exec(size)?.[1] ?? NaN);

describe("next config", () => {
  it("builds the standalone server the Dockerfile copies", () => {
    expect(config.output).toBe("standalone");
  });

  it("lets a 5 MB resume plus the rest of the form through, like the API", () => {
    expect(config.experimental?.serverActions?.bodySizeLimit).toBe(FORM_BODY_LIMIT);
    expect(megabytes(FORM_BODY_LIMIT)).toBeGreaterThanOrEqual(6);
  });

  it("does not announce the framework in every answer", () => {
    expect(config.poweredByHeader).toBe(false);
  });
});

describe("package", () => {
  it("pins the framework and the beta sign-in library exactly", () => {
    for (const name of ["next", "next-auth", "react", "react-dom"] as const) {
      expect(pkg.dependencies[name]).toMatch(/^\d/);
    }
  });

  it("has the scripts the team runs", () => {
    expect(Object.keys(pkg.scripts)).toEqual(expect.arrayContaining(["dev", "build", "start", "typecheck", "test"]));
  });
});
