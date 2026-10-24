import type { HistoryEntry, KeyValueStore } from './types';

export const HISTORY_KEY = 'talnex.history';
export const MAX_HISTORY = 20;

export interface HistoryState {
  entries: HistoryEntry[]; // newest first, at most MAX_HISTORY, never the message text
  sentCount: number; // messages delivered since the app was set up
}

export const emptyHistory: HistoryState = { entries: [], sentCount: 0 };

export function addEntry(state: HistoryState, entry: HistoryEntry, max: number = MAX_HISTORY): HistoryState {
  return {
    entries: [entry, ...state.entries.filter((e) => e.id !== entry.id)].slice(0, max),
    sentCount: state.sentCount + (entry.status === 'sent' ? 1 : 0),
  };
}

/** A waiting message got through later: its line turns to "sent". */
export function markSent(state: HistoryState, id: string): HistoryState {
  const target = state.entries.find((e) => e.id === id);
  if (!target || target.status === 'sent') return state;
  return {
    entries: state.entries.map((e) =>
      e.id === id ? { id: e.id, from: e.from, receivedAt: e.receivedAt, status: 'sent' } : e,
    ),
    sentCount: state.sentCount + 1,
  };
}

/** A waiting message was given up on: its line keeps "failed" with the final reason. */
export function markFailed(state: HistoryState, id: string, reason: string): HistoryState {
  return {
    ...state,
    entries: state.entries.map((e) => (e.id === id ? { ...e, status: 'failed', reason } : e)),
  };
}

function isEntry(x: unknown): x is HistoryEntry {
  if (!x || typeof x !== 'object') return false;
  const e = x as Partial<HistoryEntry>;
  return (
    typeof e.id === 'string' &&
    typeof e.from === 'string' &&
    typeof e.receivedAt === 'string' &&
    (e.status === 'sent' || e.status === 'failed')
  );
}

export async function loadHistory(store: KeyValueStore): Promise<HistoryState> {
  try {
    const raw = await store.get(HISTORY_KEY);
    if (!raw) return emptyHistory;
    const parsed = JSON.parse(raw) as Partial<HistoryState>;
    if (!Array.isArray(parsed.entries)) return emptyHistory;
    const sentCount = Number(parsed.sentCount);
    return {
      entries: parsed.entries.filter(isEntry).slice(0, MAX_HISTORY),
      sentCount: Number.isFinite(sentCount) && sentCount > 0 ? Math.floor(sentCount) : 0,
    };
  } catch {
    return emptyHistory;
  }
}

export async function saveHistory(store: KeyValueStore, state: HistoryState): Promise<void> {
  await store.set(HISTORY_KEY, JSON.stringify(state));
}
