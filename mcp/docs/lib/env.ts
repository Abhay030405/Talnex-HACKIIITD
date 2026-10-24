// The one place the docs site reads its settings. Server-side only: nothing here reaches the browser.
// Values come from the environment, then from the repository's .env (the nearest one above this site) for anything not
// set. The .env is only read, never copied or printed.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { parseEnv } from 'node:util';

export interface DocsSettings {
  /** TALNEX_DOCS_DEV_TOKENS=true turns on the "Get a test token" helper. Off by default. */
  devTokens: boolean;
  /** Needed only for test tokens: the API's AUTH_SECRET. Never sent to the browser. */
  authSecret: string;
  /** How long a test token lasts, in minutes (TALNEX_DOCS_DEV_TOKEN_MINUTES). */
  devTokenMinutes: number;
  /** The API addresses the playground may send requests to (TALNEX_DOCS_API_ORIGINS, comma separated). */
  apiOrigins: string[];
}

let cached: DocsSettings | undefined;

function repoEnv(): Record<string, string | undefined> {
  for (let dir = dirname(process.cwd()); ; dir = dirname(dir)) {
    const file = join(dir, '.env');
    if (existsSync(file)) return parseEnv(readFileSync(file, 'utf8'));
    if (dirname(dir) === dir) return {};
  }
}

export function docsSettings(): DocsSettings {
  if (cached) return cached;
  const fromFile = repoEnv();
  const get = (name: string) => (process.env[name] ?? fromFile[name] ?? '').trim();
  const minutes = Number(get('TALNEX_DOCS_DEV_TOKEN_MINUTES') || '30');
  cached = {
    devTokens: get('TALNEX_DOCS_DEV_TOKENS').toLowerCase() === 'true',
    authSecret: get('AUTH_SECRET'),
    devTokenMinutes: Number.isFinite(minutes) && minutes > 0 ? Math.min(minutes, 24 * 60) : 30,
    apiOrigins: get('TALNEX_DOCS_API_ORIGINS').split(',').map((o) => o.trim().replace(/\/+$/, '')).filter(Boolean),
  };
  return cached;
}
