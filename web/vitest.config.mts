import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": here("."),
      // Outside Next.js the real guard would refuse every server file; the app itself still uses the real one.
      "server-only": here("tests/support/server-only.ts"),
    },
  },
  test: { include: ["tests/**/*.test.ts"] },
});
