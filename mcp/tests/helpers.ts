// Shared test setup: ids, an API pointed at the fake, and a real MCP client talking to our server in memory.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import { TalnexApi } from "../src/api.js";
import { buildServer } from "../src/server.js";
import type { Role } from "../src/settings.js";
import { TOOLS } from "../src/tools.js";

export const SECRET = "test-secret-not-real";
export const EVENT = "11111111-1111-4111-8111-111111111111";
export const PROJECT = "22222222-2222-4222-8222-222222222222";
export const CAND = "33333333-3333-4333-8333-333333333333";
export const ROLE = "44444444-4444-4444-8444-444444444444";
export const WALK = "55555555-5555-4555-8555-555555555555";

export function apiFor(url: string, role: Role = "organizer"): TalnexApi {
  return new TalnexApi({ apiUrl: url, secret: SECRET, email: `${role}@talnex.test`, role });
}

/** Call a tool's code directly, skipping the MCP layer. */
export function run(name: string, api: TalnexApi, args: Record<string, unknown> = {}) {
  const t = TOOLS.find((x) => x.name === name);
  if (!t) throw new Error(`no tool ${name}`);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return t.run(api, args as any);
}

export interface Called {
  isError: boolean;
  text: string;
  json: unknown;
}

/** A real MCP client connected to our server. call() returns the text; a protocol error becomes isError too. */
export async function connect(api: TalnexApi) {
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await buildServer(api).connect(serverSide);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(clientSide);
  return {
    client,
    async call(name: string, args: Record<string, unknown> = {}): Promise<Called> {
      try {
        const r = await client.callTool({ name, arguments: args });
        const text = (r.content as { type: string; text: string }[]).map((c) => c.text).join("\n");
        let json: unknown = null;
        try {
          json = JSON.parse(text);
        } catch { /* plain words */ }
        return { isError: r.isError === true, text, json };
      } catch (e) {
        return { isError: true, text: e instanceof Error ? e.message : String(e), json: null };
      }
    },
    close: () => client.close(),
  };
}
