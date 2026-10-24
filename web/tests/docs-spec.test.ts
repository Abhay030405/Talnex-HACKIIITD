// The docs' API reference is built from a copy of the Go API's spec (the website's Docker build only sees web/).
// This fails while the copy is behind backend/api/openapi.yaml: run `npm run docs:generate` and commit the result.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const spec = join(__dirname, "..", "..", "backend", "api", "openapi.yaml");
const copy = join(__dirname, "..", "content", "openapi.yaml");
const text = (file: string) => readFileSync(file, "utf8").replace(/\r\n/g, "\n");

describe("docs API reference", () => {
  it.skipIf(!existsSync(spec))("uses the current API spec", () => {
    expect(text(copy)).toBe(text(spec));
  });
});
