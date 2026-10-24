// A tiny stand-in for the Go API: answers from a route table and remembers every request it got.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export interface Seen {
  method: string;
  path: string;
  auth: string;
  contentType: string;
  body: string;
}

export type Handler = (req: IncomingMessage, res: ServerResponse, body: string) => void;

export class FakeApi {
  seen: Seen[] = [];
  routes = new Map<string, Handler>();
  private server?: Server;
  url = "";

  json(method: string, path: string, status: number, value: unknown): this {
    this.routes.set(`${method} ${path}`, (_req, res) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(value));
    });
    return this;
  }

  on(method: string, path: string, handler: Handler): this {
    this.routes.set(`${method} ${path}`, handler);
    return this;
  }

  /** Every route answers with this status and body, as when the API or its database is in trouble. */
  failing?: Handler;
  failAll(status: number, value: unknown): this {
    this.failing = (_req, res) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(value));
    };
    return this;
  }

  async start(): Promise<this> {
    this.server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8");
        const path = (req.url ?? "").split("?")[0];
        this.seen.push({ method: req.method ?? "", path, auth: req.headers.authorization ?? "",
                         contentType: req.headers["content-type"] ?? "", body });
        const handler = this.failing ?? this.routes.get(`${req.method} ${path}`);
        if (!handler) {
          res.writeHead(404, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "not found" }));
          return;
        }
        handler(req, res, body);
      });
    });
    await new Promise<void>((r) => this.server!.listen(0, "127.0.0.1", r));
    this.url = `http://127.0.0.1:${(this.server!.address() as AddressInfo).port}`;
    return this;
  }

  async stop(): Promise<void> {
    this.server?.closeAllConnections?.();
    await new Promise<void>((r) => this.server?.close(() => r()) ?? r());
  }

  posts(): Seen[] {
    return this.seen.filter((s) => s.method !== "GET");
  }
}
