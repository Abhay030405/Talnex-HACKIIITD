import type { HistoryEntry } from '../types';

/** "just now", "5 min ago", "3 h ago", or the date and time for anything older than a day. */
export function formatWhen(iso: string, now: number = Date.now()): string {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return 'unknown time';
  const minutes = Math.floor((now - at) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
  return new Date(at).toLocaleString();
}

export function entryStatus(entry: HistoryEntry): { text: string; good: boolean } {
  if (entry.status === 'sent') return { text: 'sent', good: true };
  return { text: `failed: ${entry.reason ?? 'unknown'}`, good: false };
}

export function waitingLine(pending: number): string {
  if (pending === 0) return 'Nothing waiting.';
  return pending === 1 ? '1 message waiting to be sent.' : `${pending} messages waiting to be sent.`;
}
