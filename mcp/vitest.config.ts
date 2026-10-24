import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// "@/..." lets a test import the website's own web/lib/token.ts, to prove our token matches it byte for byte. Its
// "jose" comes from this package, since the website's node_modules may not be installed.
export default defineConfig({
  resolve: {
    alias: [
      { find: /^@\//, replacement: `${fileURLToPath(new URL("../web/", import.meta.url))}` },
      { find: /^jose$/, replacement: fileURLToPath(new URL("./node_modules/jose/dist/webapi/index.js", import.meta.url)) },
    ],
  },
  test: {
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/index.ts"], // the stdio entry point; the e2e script runs it for real
      reporter: ["text", "text-summary"],
    },
  },
});
