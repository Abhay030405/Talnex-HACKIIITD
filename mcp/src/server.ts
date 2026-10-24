// Wires the tools into an MCP server. A failed call comes back as a tool error with plain words, never a stack trace.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { ApiError, type TalnexApi } from "./api.js";
import { roleProblem, TOOLS } from "./tools.js";

export const SERVER_INFO = { name: "talnex", version: "0.1.0" };

export function toolResult(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 1) }] };
}

export function toolError(e: unknown) {
  const message = e instanceof ApiError ? e.message : "Something went wrong in the TalNex MCP server.";
  return { content: [{ type: "text" as const, text: message }], isError: true };
}

export function buildServer(api: TalnexApi): McpServer {
  const server = new McpServer(SERVER_INFO);
  for (const t of TOOLS) {
    server.registerTool(
      t.name,
      { title: t.title, description: t.description, inputSchema: t.input,
        annotations: { readOnlyHint: t.readOnly, openWorldHint: false } },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      async (args: any) => {
        const refused = roleProblem(t, api.settings.role);
        if (refused) return toolError(new ApiError(refused, 403));
        try {
          return toolResult(await t.run(api, args ?? {}));
        } catch (e) {
          return toolError(e);
        }
      },
    );
  }
  return server;
}
