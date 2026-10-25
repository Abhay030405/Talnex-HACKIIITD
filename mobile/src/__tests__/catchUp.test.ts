import { CURSOR_KEY, CatchUp, SEEN_KEY, fingerprint } from '../catchUp';
import type { IncomingSms } from '../types';
import { memStore } from './memStore';

const T0 = Date.parse('2026-05-01T10:00:00Z');
const min = (n: number) => n * 60_000;
const text = (body: string, at: number, from = '+911'): IncomingSms => ({ from, body, receivedAt: new Date(at) });

function make(inbox: IncomingSms[], startAt = T0) {
  const store = memStore();
  let now = startAt;
  const forwarded: IncomingSms[] = [];
  const reads: number[] = [];
  const catchUp = new CatchUp({
    store,
    readInbox: async (since) => {
      reads.push(since);
      return inbox.filter((s) => s.receivedAt.getTime() > since);
    },
    forward: async (sms) => {
      forwarded.push(sms);
    },
    now: () => now,
  });
  return { catchUp, store, forwarded, reads, setNow: (t: number) => (now = t) };
}

describe('fingerprint', () => {
  it('is short, stable and hides the words', () => {
    const f = fingerprint('+911', 'Your code is 482913');
    expect(f).toMatch(/^[0-9a-f]{8}$/);
    expect(fingerprint(' +911 ', 'Your code is 482913')).toBe(f);
    expect(fingerprint('+911', 'Your code is 482914')).not.toBe(f);
  });
});

describe('CatchUp', () => {
  it('does nothing while listening has never been turned on', async () => {
    const { catchUp, forwarded, reads } = make([text('a', T0 + 1000)]);
    await catchUp.load();
    expect(await catchUp.run()).toBe(0);
    expect(forwarded).toHaveLength(0);
    expect(reads).toHaveLength(0);
  });

  it('never sends texts from before listening was turned on', async () => {
    const { catchUp, forwarded, setNow } = make([text('old', T0 - min(5)), text('new', T0 + min(1))]);
    await catchUp.load();
    await catchUp.begin();
    setNow(T0 + min(2));
    expect(await catchUp.run()).toBe(1);
    expect(forwarded.map((s) => s.body)).toEqual(['new']);
  });

  it('sends what arrived while the app was dead, with the inbox time, and only once', async () => {
    const inbox = [text('missed 1', T0 + min(1)), text('missed 2', T0 + min(3))];
    const { catchUp, forwarded, setNow } = make(inbox);
    await catchUp.load();
    await catchUp.begin();
    setNow(T0 + min(10));
    expect(await catchUp.run()).toBe(2);
    expect(forwarded.map((s) => s.receivedAt.getTime())).toEqual([T0 + min(1), T0 + min(3)]);
    expect(await catchUp.run()).toBe(0);
    expect(forwarded).toHaveLength(2);
  });

  it('skips texts the live listener already sent, matching each one once', async () => {
    const inbox = [text('code 1', T0 + min(1)), text('code 1', T0 + min(2)), text('code 2', T0 + min(3))];
    const { catchUp, forwarded, setNow } = make(inbox);
    await catchUp.load();
    await catchUp.begin();
    catchUp.noteLive(text('code 1', T0 + min(1) + 3000));
    catchUp.noteLive(text('code 2', T0 + min(3) - 2000));
    setNow(T0 + min(5));
    expect(await catchUp.run()).toBe(1);
    expect(forwarded.map((s) => s.body)).toEqual(['code 1']);
  });

  it('keeps the cursor through a restart, so a killed app still catches up', async () => {
    const inbox = [text('while dead', T0 + min(30))];
    const first = make(inbox);
    await first.catchUp.load();
    await first.catchUp.begin();

    const now = T0 + min(40);
    const forwarded: IncomingSms[] = [];
    const again = new CatchUp({
      store: first.store,
      readInbox: async (since) => inbox.filter((s) => s.receivedAt.getTime() > since),
      forward: async (sms) => {
        forwarded.push(sms);
      },
      now: () => now,
    });
    await again.load();
    await again.begin();
    expect(await again.run()).toBe(1);
    expect(forwarded[0].body).toBe('while dead');
  });

  it('remembers live texts across a restart, without storing their words', async () => {
    const inbox = [text('secret code 1', T0 + min(1))];
    const first = make(inbox);
    await first.catchUp.load();
    await first.catchUp.begin();
    first.catchUp.noteLive(text('secret code 1', T0 + min(1)));
    await first.catchUp.end();
    await first.catchUp.begin();
    expect(first.store.data.get(SEEN_KEY)).not.toContain('secret');

    const forwarded: IncomingSms[] = [];
    const again = new CatchUp({
      store: first.store,
      readInbox: async () => inbox,
      forward: async (sms) => {
        forwarded.push(sms);
      },
      now: () => T0 + min(2),
    });
    await again.load();
    expect(await again.run()).toBe(0);
    expect(forwarded).toHaveLength(0);
  });

  it('forgets the cursor when listening is turned off', async () => {
    const { catchUp, store, forwarded, setNow } = make([text('while off', T0 + min(5))]);
    await catchUp.load();
    await catchUp.begin();
    await catchUp.end();
    expect(store.data.has(CURSOR_KEY)).toBe(false);
    setNow(T0 + min(10));
    await catchUp.begin();
    setNow(T0 + min(11));
    expect(await catchUp.run()).toBe(0);
    expect(forwarded).toHaveLength(0);
  });

  it('never reads further back than a day', async () => {
    const { catchUp, reads, setNow } = make([]);
    await catchUp.load();
    await catchUp.begin();
    setNow(T0 + min(60 * 30));
    await catchUp.run();
    expect(reads[0]).toBe(T0 + min(60 * 30) - min(60 * 24));
  });

  it('runs one catch-up at a time', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const store = memStore();
    let reads = 0;
    const catchUp = new CatchUp({
      store,
      readInbox: async () => {
        reads++;
        await gate;
        return [];
      },
      forward: async () => {},
      now: () => T0,
    });
    await catchUp.begin();
    const first = catchUp.run();
    expect(await catchUp.run()).toBe(0);
    release();
    await first;
    expect(reads).toBe(1);
  });

  it('ignores a broken saved list', async () => {
    const { catchUp, store, forwarded, setNow } = make([text('a', T0 + min(1))]);
    store.data.set(SEEN_KEY, '{nope');
    await catchUp.load();
    await catchUp.begin();
    setNow(T0 + min(2));
    expect(await catchUp.run()).toBe(1);
    expect(forwarded).toHaveLength(1);
  });
});
