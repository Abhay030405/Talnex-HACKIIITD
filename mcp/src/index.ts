#!/usr/bin/env node
// Start the TalNex MCP server on stdio:  node mcp/dist/index.js  (settings come from the environment, see README.md)
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { TalnexApi } from "./api.js";
import { buildServer } from "./server.js";
import { loadSettings, SettingsError } from "./settings.js";

async function main(): Promise<void> {
  let settings;
  try {
    settings = loadSettings();
  } catch (e) {
    // stdout belongs to the MCP protocol, so problems go to stderr
    console.error(e instanceof SettingsError ? e.message : String(e));
    process.exit(1);
  }
  const server = buildServer(new TalnexApi(settings));
  await server.connect(new StdioServerTransport());
  console.error(`TalNex MCP server ready (${settings.role} ${settings.email} -> ${settings.apiUrl})`);
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : String(e));
  process.exit(1);
});
