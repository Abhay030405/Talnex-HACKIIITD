import { describeResult, isRetryable, shortReason } from './gateway';
import { addEntry, emptyHistory, loadHistory, markFailed, markSent, saveHistory, type HistoryState } from './history';
import { buildPayload } from './payload';
import { addToQueue, bumpAttempts, loadQueue, makeQueued, removeFromQueue, saveQueue, splitStale } from './queue';
import type { GatewayPayload, IncomingSms, KeyValueStore, QueuedMessage, SendResult, Settings } from './types';

export interface RelayDeps {
  store: KeyValueStore;
  getSettings: () => Promise<Settings>;
  send: (settings: Settings, payload: GatewayPayload) => Promise<SendResult>;
  newId?: () => string;
  now?: () => number;
}

export interface RelayState {
  history: HistoryState;
  pending: number;
}

export const STALE_REASON = 'too old, dropped';

/**
 * The app's logic, with no screens and no phone code: send each text, keep it if sending fails,
 * and send the waiting ones later. Changes run one at a time, so a text arriving during a retry
 * can never overwrite what the retry saved.
 */
export class Relay {
  private history: HistoryState = emptyHistory;
  private queue: QueuedMessage[] = [];
  private listeners = new Set<(s: RelayState) => void>();
  private chain: Promise<unknown> = Promise.resolve();
  private retrying = false;
  private counter = 0;

  constructor(private readonly deps: RelayDeps) {}

  state(): RelayState {
    return { history: this.history, pending: this.queue.length };
  }

  subscribe(fn: (s: RelayState) => void): () => void {
    this.listeners.add(fn);
    fn(this.state());
    return () => {
      this.listeners.delete(fn);
    };
  }

  load(): Promise<void> {
    return this.serial(async () => {
      this.history = await loadHistory(this.deps.store);
      this.queue = await loadQueue(this.deps.store);
      this.emit();
    });
  }

  /** Called for every text the SIM receives. A new text is always tried at once, even if older ones wait. */
  async handleIncoming(sms: IncomingSms): Promise<SendResult> {
    const settings = await this.deps.getSettings();
    const payload = buildPayload(sms, settings.deviceName);
    const id = this.makeId();
    const result = await this.deps.send(settings, payload);

    await this.serial(async () => {
      const base = { id, from: payload.from, receivedAt: payload.received_at };
      if (result.outcome === 'ok') {
        this.history = addEntry(this.history, { ...base, status: 'sent' });
      } else {
        this.history = addEntry(this.history, { ...base, status: 'failed', reason: shortReason(result) });
        if (isRetryable(result)) {
          this.queue = addToQueue(this.queue, makeQueued(id, payload));
          await saveQueue(this.deps.store, this.queue);
        }
      }
      await saveHistory(this.deps.store, this.history);
      this.emit();
    });
    return result;
  }

  /**
   * Sends the waiting messages, oldest first. Messages older than a day and messages the server refused
   * are dropped. Stops at the first failure that may pass later, because the server is still away.
   * A call made while a retry is already running returns at once.
   */
  async retryPending(): Promise<{ sent: number; left: number }> {
    if (this.retrying) return { sent: 0, left: this.queue.length };
    this.retrying = true;
    try {
      return await this.serial(() => this.flush());
    } finally {
      this.retrying = false;
    }
  }

  /** "Send test message" on the Settings screen. Not queued and not counted. */
  async sendTest(settings: Settings, payload: GatewayPayload): Promise<{ result: SendResult; words: string }> {
    const result = await this.deps.send(settings, payload);
    return { result, words: describeResult(result) };
  }

  private async flush(): Promise<{ sent: number; left: number }> {
    let sent = 0;
    const { fresh, stale } = splitStale(this.queue, this.now());
    let changed = stale.length > 0;
    for (const item of stale) this.history = markFailed(this.history, item.id, STALE_REASON);
    this.queue = fresh;

    if (fresh.length > 0) {
      const settings = await this.deps.getSettings();
      for (const item of fresh) {
        const result = await this.deps.send(settings, {
          ...item.payload,
          device: settings.deviceName.trim() || item.payload.device,
        });
        changed = true;
        if (result.outcome === 'ok') {
          this.queue = removeFromQueue(this.queue, item.id);
          this.history = markSent(this.history, item.id);
          sent++;
        } else if (!isRetryable(result)) {
          this.queue = removeFromQueue(this.queue, item.id);
          this.history = markFailed(this.history, item.id, shortReason(result));
        } else {
          this.queue = bumpAttempts(this.queue, item.id);
          this.history = markFailed(this.history, item.id, shortReason(result));
          break;
        }
      }
    }

    if (changed) {
      await saveQueue(this.deps.store, this.queue);
      await saveHistory(this.deps.store, this.history);
      this.emit();
    }
    return { sent, left: this.queue.length };
  }

  private serial<T>(task: () => Promise<T>): Promise<T> {
    const run = this.chain.then(task, task);
    this.chain = run.catch(() => undefined);
    return run;
  }

  private emit(): void {
    const s = this.state();
    this.listeners.forEach((fn) => fn(s));
  }

  private makeId(): string {
    return this.deps.newId ? this.deps.newId() : `${this.now()}-${this.counter++}`;
  }

  private now(): number {
    return this.deps.now ? this.deps.now() : Date.now();
  }
}
