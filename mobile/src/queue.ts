import type { GatewayPayload, KeyValueStore, QueuedMessage } from './types';

export const QUEUE_KEY = 'talnex.queue';
// The oldest messages go first past this, so the phone never fills up.
export const MAX_QUEUE = 200;
// The server deletes texts after 24 hours, so a sign-up code older than that is no use to anyone.
export const MAX_QUEUE_AGE_MS = 24 * 60 * 60 * 1000;

export function makeQueued(id: string, payload: GatewayPayload): QueuedMessage {
  return { id, payload, attempts: 1 };
}

/** Adds one message at the end (replacing one with the same id) and drops the oldest past `max`. */
export function addToQueue(queue: QueuedMessage[], item: QueuedMessage, max: number = MAX_QUEUE): QueuedMessage[] {
  const next = [...queue.filter((q) => q.id !== item.id), item];
  return next.slice(Math.max(0, next.length - max));
}

export function removeFromQueue(queue: QueuedMessage[], id: string): QueuedMessage[] {
  return queue.filter((q) => q.id !== id);
}

export function bumpAttempts(queue: QueuedMessage[], id: string): QueuedMessage[] {
  return queue.map((q) => (q.id === id ? { ...q, attempts: q.attempts + 1 } : q));
}

/** Splits the queue into messages still worth sending and ones too old to matter. */
export function splitStale(
  queue: QueuedMessage[],
  now: number = Date.now(),
  maxAgeMs: number = MAX_QUEUE_AGE_MS,
): { fresh: QueuedMessage[]; stale: QueuedMessage[] } {
  const fresh: QueuedMessage[] = [];
  const stale: QueuedMessage[] = [];
  for (const q of queue) {
    const at = Date.parse(q.payload.received_at);
    (Number.isNaN(at) || now - at > maxAgeMs ? stale : fresh).push(q);
  }
  return { fresh, stale };
}

function isQueued(x: unknown): x is QueuedMessage {
  if (!x || typeof x !== 'object') return false;
  const { id, attempts, payload } = x as Partial<QueuedMessage>;
  return (
    typeof id === 'string' &&
    typeof attempts === 'number' &&
    !!payload &&
    typeof payload.from === 'string' &&
    typeof payload.body === 'string' &&
    typeof payload.received_at === 'string' &&
    typeof payload.device === 'string'
  );
}

/** A broken or old-format saved queue is ignored instead of crashing the app. */
export async function loadQueue(store: KeyValueStore): Promise<QueuedMessage[]> {
  try {
    const raw = await store.get(QUEUE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isQueued).slice(-MAX_QUEUE) : [];
  } catch {
    return [];
  }
}

/** An empty queue is removed, so no message text stays on the phone once everything is sent. */
export async function saveQueue(store: KeyValueStore, queue: QueuedMessage[]): Promise<void> {
  if (queue.length === 0) await store.remove(QUEUE_KEY);
  else await store.set(QUEUE_KEY, JSON.stringify(queue));
}
