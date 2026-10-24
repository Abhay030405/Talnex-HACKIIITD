import { addEntry, emptyHistory, loadHistory, markFailed, markSent, saveHistory, HISTORY_KEY } from '../history';
import {
  addToQueue,
  bumpAttempts,
  loadQueue,
  makeQueued,
  QUEUE_KEY,
  removeFromQueue,
  saveQueue,
  splitStale,
} from '../queue';
import type { GatewayPayload, HistoryEntry } from '../types';
import { memStore } from './memStore';

const payload = (receivedAt = '2026-05-01T10:00:00.000Z'): GatewayPayload => ({
  from: 'AX-BANK',
  body: 'code 1',
  received_at: receivedAt,
  device: 'Spare',
});
const entry = (id: string, status: HistoryEntry['status'] = 'sent'): HistoryEntry => ({
  id,
  from: 'AX-BANK',
  receivedAt: '2026-05-01T10:00:00.000Z',
  status,
  ...(status === 'failed' ? { reason: 'cannot reach server' } : {}),
});

describe('queue', () => {
  it('keeps order and drops the oldest past the limit', () => {
    let q = addToQueue([], makeQueued('1', payload()), 2);
    q = addToQueue(q, makeQueued('2', payload()), 2);
    q = addToQueue(q, makeQueued('3', payload()), 2);
    expect(q.map((x) => x.id)).toEqual(['2', '3']);
  });

  it('replaces a message with the same id instead of doubling it', () => {
    const q = addToQueue([makeQueued('1', payload())], makeQueued('1', payload()));
    expect(q).toHaveLength(1);
  });

  it('removes and counts attempts', () => {
    const q = [makeQueued('1', payload()), makeQueued('2', payload())];
    expect(removeFromQueue(q, '1').map((x) => x.id)).toEqual(['2']);
    expect(bumpAttempts(q, '2')[1].attempts).toBe(2);
    expect(q[1].attempts).toBe(1);
  });

  it('separates messages older than a day', () => {
    const now = Date.parse('2026-05-02T12:00:00Z');
    const { fresh, stale } = splitStale(
      [
        makeQueued('old', payload('2026-05-01T11:00:00.000Z')),
        makeQueued('new', payload('2026-05-02T11:00:00.000Z')),
        makeQueued('bad', payload('not a time')),
      ],
      now,
    );
    expect(fresh.map((q) => q.id)).toEqual(['new']);
    expect(stale.map((q) => q.id)).toEqual(['old', 'bad']);
  });

  it('saves, reloads and removes the key when empty', async () => {
    const store = memStore();
    await saveQueue(store, [makeQueued('1', payload())]);
    expect(await loadQueue(store)).toEqual([makeQueued('1', payload())]);
    await saveQueue(store, []);
    expect(store.data.has(QUEUE_KEY)).toBe(false);
  });

  it('ignores a broken saved queue and broken items', async () => {
    const store = memStore();
    store.data.set(QUEUE_KEY, '{not json');
    expect(await loadQueue(store)).toEqual([]);
    store.data.set(QUEUE_KEY, JSON.stringify([makeQueued('ok', payload()), { id: 'x' }, null, 5]));
    expect((await loadQueue(store)).map((q) => q.id)).toEqual(['ok']);
  });
});

describe('history', () => {
  it('keeps the newest 20 and counts every sent one', () => {
    let h = emptyHistory;
    for (let i = 0; i < 25; i++) h = addEntry(h, entry(String(i)));
    expect(h.entries).toHaveLength(20);
    expect(h.entries[0].id).toBe('24');
    expect(h.sentCount).toBe(25);
  });

  it('turns a failed line into sent once, without the old reason', () => {
    let h = addEntry(emptyHistory, entry('a', 'failed'));
    expect(h.sentCount).toBe(0);
    h = markSent(h, 'a');
    expect(h.entries[0]).toEqual(entry('a', 'sent'));
    expect(h.sentCount).toBe(1);
    expect(markSent(h, 'a')).toBe(h);
    expect(markSent(h, 'missing')).toBe(h);
  });

  it('records the final reason when a message is given up', () => {
    const h = markFailed(addEntry(emptyHistory, entry('a', 'failed')), 'a', 'too old, dropped');
    expect(h.entries[0]).toMatchObject({ status: 'failed', reason: 'too old, dropped' });
  });

  it('saves and reloads, and survives junk', async () => {
    const store = memStore();
    const h = addEntry(addEntry(emptyHistory, entry('a')), entry('b', 'failed'));
    await saveHistory(store, h);
    expect(await loadHistory(store)).toEqual(h);

    store.data.set(HISTORY_KEY, 'nope');
    expect(await loadHistory(store)).toEqual(emptyHistory);
    store.data.set(HISTORY_KEY, JSON.stringify({ entries: [entry('ok'), { id: 1 }], sentCount: 'lots' }));
    expect(await loadHistory(store)).toEqual({ entries: [entry('ok')], sentCount: 0 });
  });
});
