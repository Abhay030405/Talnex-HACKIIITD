import type { IncomingSms, KeyValueStore } from './types';

export const CURSOR_KEY = 'talnex.inboxCursor';
export const SEEN_KEY = 'talnex.seen';
// The server deletes texts after a day, so older ones are never worth sending.
export const MAX_CATCH_UP_AGE_MS = 24 * 60 * 60 * 1000;
// The live listener's time and the inbox time of the same text differ by a few seconds at most.
export const SAME_TEXT_WINDOW_MS = 10 * 60 * 1000;
export const MAX_SEEN = 500;

/** A text forwarded live, remembered without its words: only a fingerprint and the time. */
export interface SeenText {
  f: string;
  at: number;
}

/** A short fingerprint of sender and text (FNV-1a), so the words themselves are never stored. */
export function fingerprint(from: string, body: string): string {
  let hash = 0x811c9dc5;
  const text = `${from.trim()}\u0000${body}`;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

export interface CatchUpDeps {
  store: KeyValueStore;
  readInbox: (sinceMs: number) => Promise<IncomingSms[]>;
  forward: (sms: IncomingSms) => Promise<unknown>;
  now?: () => number;
}

/**
 * Sends the texts that reached the phone while the app was not running, read back from the SMS inbox.
 *
 * The cursor is the inbox time already handled. It exists only while listening is on, so turning listening off
 * and on again never sends what arrived in between. Texts the live listener already forwarded are skipped by
 * fingerprint, each fingerprint matching one inbox text at most.
 */
export class CatchUp {
  private seen: SeenText[] = [];
  private chain: Promise<unknown> = Promise.resolve();
  private running = false;

  constructor(private readonly deps: CatchUpDeps) {}

  async load(): Promise<void> {
    this.seen = await loadSeen(this.deps.store);
  }

  /** Listening was turned on. Keeps an existing cursor, so a restart after the app was killed still catches up. */
  begin(): Promise<void> {
    return this.serial(async () => {
      if ((await this.cursor()) === null) await this.saveCursor(this.now());
    });
  }

  /** Listening was turned off. */
  end(): Promise<void> {
    return this.serial(() => this.deps.store.remove(CURSOR_KEY));
  }

  /** Called for each live text, before it is sent, so a catch-up running at the same time skips it. */
  noteLive(sms: IncomingSms): void {
    this.seen.push({ f: fingerprint(sms.from, sms.body), at: sms.receivedAt.getTime() });
    void this.serial(() => this.saveSeen());
  }

  /** Sends what was missed. Returns how many texts were sent. A call made while one is running returns 0. */
  async run(): Promise<number> {
    if (this.running) return 0;
    this.running = true;
    try {
      return await this.serial(() => this.catchUp());
    } finally {
      this.running = false;
    }
  }

  private async catchUp(): Promise<number> {
    const cursor = await this.cursor();
    if (cursor === null) return 0;
    const now = this.now();
    const from = Math.max(cursor, now - MAX_CATCH_UP_AGE_MS);
    const inbox = await this.deps.readInbox(from);

    let sent = 0;
    let newCursor = from;
    for (const sms of inbox) {
      const at = sms.receivedAt.getTime();
      if (at <= from) continue;
      if (!this.takeSeen(sms)) {
        await this.deps.forward(sms);
        this.seen.push({ f: fingerprint(sms.from, sms.body), at });
        sent++;
      }
      newCursor = Math.max(newCursor, at);
    }
    await this.saveCursor(newCursor);
    await this.saveSeen();
    return sent;
  }

  /** Finds and uses up a live text matching this inbox text. */
  private takeSeen(sms: IncomingSms): boolean {
    const f = fingerprint(sms.from, sms.body);
    const at = sms.receivedAt.getTime();
    const i = this.seen.findIndex((s) => s.f === f && Math.abs(s.at - at) <= SAME_TEXT_WINDOW_MS);
    if (i < 0) return false;
    this.seen.splice(i, 1);
    return true;
  }

  private async cursor(): Promise<number | null> {
    const raw = await this.deps.store.get(CURSOR_KEY);
    const value = raw === null ? NaN : Number(raw);
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  private saveCursor(at: number): Promise<void> {
    return this.deps.store.set(CURSOR_KEY, String(Math.floor(at)));
  }

  private saveSeen(): Promise<void> {
    const cut = this.now() - MAX_CATCH_UP_AGE_MS;
    this.seen = this.seen.filter((s) => s.at > cut).slice(-MAX_SEEN);
    return this.deps.store.set(SEEN_KEY, JSON.stringify(this.seen));
  }

  private serial<T>(task: () => Promise<T>): Promise<T> {
    const run = this.chain.then(task, task);
    this.chain = run.catch(() => undefined);
    return run;
  }

  private now(): number {
    return this.deps.now ? this.deps.now() : Date.now();
  }
}

async function loadSeen(store: KeyValueStore): Promise<SeenText[]> {
  try {
    const parsed: unknown = JSON.parse((await store.get(SEEN_KEY)) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (s): s is SeenText => !!s && typeof s.f === 'string' && typeof s.at === 'number' && Number.isFinite(s.at),
    );
  } catch {
    return [];
  }
}
