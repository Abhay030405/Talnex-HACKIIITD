import { HISTORY_KEY } from '../history';
import { QUEUE_KEY } from '../queue';
import { Relay, STALE_REASON, type RelayState } from '../relay';
import type { GatewayPayload, SendResult, Settings } from '../types';
import { memStore } from './memStore';

const settings: Settings = {
  gatewayUrl: 'http://10.0.0.5:8080/v1/sms/incoming',
  gatewayKey: 'gateway-key-0123456789',
  deviceName: 'Spare',
};
const NOW = Date.parse('2026-05-01T12:00:00Z');
const sms = (body = 'code 999', minutesAgo = 1) => ({
  from: '+911',
  body,
  receivedAt: new Date(NOW - minutesAgo * 60_000),
});

function make(answers: SendResult[], store = memStore()) {
  const sent: GatewayPayload[] = [];
  const send = jest.fn(async (_s: Settings, p: GatewayPayload) => {
    sent.push(p);
    return answers.shift() ?? { outcome: 'ok' as const, status: 202 };
  });
  let n = 0;
  const relay = new Relay({ store, getSettings: async () => settings, send, newId: () => `id${n++}`, now: () => NOW });
  return { relay, store, send, sent };
}

describe('Relay.handleIncoming', () => {
  it('sends, counts and keeps nothing waiting', async () => {
    const { relay, sent } = make([{ outcome: 'ok', status: 202 }]);
    await relay.load();
    await relay.handleIncoming(sms());
    expect(sent[0]).toMatchObject({ from: '+911', body: 'code 999', device: 'Spare' });
    expect(relay.state().pending).toBe(0);
    expect(relay.state().history.sentCount).toBe(1);
    expect(relay.state().history.entries[0]).toMatchObject({ status: 'sent' });
  });

  it('keeps a failed message and never writes its text into the history', async () => {
    const { relay, store } = make([{ outcome: 'unreachable' }]);
    await relay.load();
    await relay.handleIncoming(sms('secret code 999'));
    expect(relay.state().pending).toBe(1);
    expect(relay.state().history.entries[0]).toMatchObject({ status: 'failed', reason: 'cannot reach server' });
    expect(store.data.get(HISTORY_KEY)).not.toContain('secret code 999');
  });

  it('does not keep a message the server refused', async () => {
    const { relay } = make([{ outcome: 'rejected', status: 400 }]);
    await relay.load();
    await relay.handleIncoming(sms());
    expect(relay.state().pending).toBe(0);
    expect(relay.state().history.entries[0]).toMatchObject({ status: 'failed', reason: 'refused by server' });
  });

  it('tells subscribers about every change', async () => {
    const { relay } = make([]);
    const seen: RelayState[] = [];
    const stop = relay.subscribe((s) => seen.push(s));
    await relay.handleIncoming(sms());
    stop();
    await relay.handleIncoming(sms());
    expect(seen.map((s) => s.history.sentCount)).toEqual([0, 1]);
  });
});

describe('Relay.retryPending', () => {
  it('sends a waiting message later and turns its line to sent', async () => {
    const { relay, store } = make([{ outcome: 'timeout' }, { outcome: 'ok', status: 202 }]);
    await relay.load();
    await relay.handleIncoming(sms());
    expect(await relay.retryPending()).toEqual({ sent: 1, left: 0 });
    expect(relay.state().history.entries[0].status).toBe('sent');
    expect(relay.state().history.sentCount).toBe(1);
    expect(store.data.has(QUEUE_KEY)).toBe(false);
  });

  it('stops at the first failure that may pass later', async () => {
    const { relay, send } = make([
      { outcome: 'timeout' },
      { outcome: 'timeout' },
      { outcome: 'rate_limited', status: 429 },
    ]);
    await relay.load();
    await relay.handleIncoming(sms('a'));
    await relay.handleIncoming(sms('b'));
    expect(await relay.retryPending()).toEqual({ sent: 0, left: 2 });
    expect(send).toHaveBeenCalledTimes(3);
    expect(relay.state().history.entries[1]).toMatchObject({ reason: 'server busy' });
  });

  it('drops a refused message and carries on with the next', async () => {
    const { relay } = make([
      { outcome: 'unreachable' },
      { outcome: 'unreachable' },
      { outcome: 'rejected', status: 400 },
      { outcome: 'ok' },
    ]);
    await relay.load();
    await relay.handleIncoming(sms('a'));
    await relay.handleIncoming(sms('b'));
    expect(await relay.retryPending()).toEqual({ sent: 1, left: 0 });
    expect(relay.state().history.entries.map((e) => e.status)).toEqual(['sent', 'failed']);
  });

  it('drops messages older than a day without sending them', async () => {
    const { relay, send } = make([{ outcome: 'unreachable' }]);
    await relay.load();
    await relay.handleIncoming(sms('old', 25 * 60));
    expect(await relay.retryPending()).toEqual({ sent: 0, left: 0 });
    expect(send).toHaveBeenCalledTimes(1);
    expect(relay.state().history.entries[0]).toMatchObject({ status: 'failed', reason: STALE_REASON });
  });

  it('uses the current phone name when resending', async () => {
    const store = memStore();
    const { relay, sent } = make([{ outcome: 'unreachable' }], store);
    await relay.load();
    await relay.handleIncoming(sms());
    const renamed = new Relay({
      store,
      getSettings: async () => ({ ...settings, deviceName: 'Renamed' }),
      send: async (_s, p) => {
        sent.push(p);
        return { outcome: 'ok' };
      },
      now: () => NOW,
    });
    await renamed.load();
    await renamed.retryPending();
    expect(sent[1].device).toBe('Renamed');
  });

  it('survives an app restart', async () => {
    const { relay, store } = make([{ outcome: 'unreachable' }]);
    await relay.load();
    await relay.handleIncoming(sms());
    const again = new Relay({
      store,
      getSettings: async () => settings,
      send: async () => ({ outcome: 'ok' }),
      now: () => NOW,
    });
    await again.load();
    expect(again.state().pending).toBe(1);
    expect(await again.retryPending()).toEqual({ sent: 1, left: 0 });
  });

  it('runs one retry at a time', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const { relay, send } = make([{ outcome: 'unreachable' }]);
    await relay.load();
    await relay.handleIncoming(sms());
    send.mockImplementationOnce(async () => {
      await gate;
      return { outcome: 'ok' };
    });
    const first = relay.retryPending();
    expect(await relay.retryPending()).toEqual({ sent: 0, left: 1 });
    release();
    expect(await first).toEqual({ sent: 1, left: 0 });
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('keeps a text that arrives during a retry', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const { relay, store, send } = make([{ outcome: 'unreachable' }]);
    await relay.load();
    await relay.handleIncoming(sms('a'));
    send.mockImplementation(async (_s, p) => {
      if (p.body === 'b') return { outcome: 'unreachable' };
      await gate;
      return { outcome: 'ok' };
    });
    const retry = relay.retryPending();
    const arriving = relay.handleIncoming(sms('b'));
    release();
    await Promise.all([retry, arriving]);
    expect(relay.state().pending).toBe(1);
    expect(JSON.parse(store.data.get(QUEUE_KEY)!)[0].payload.body).toBe('b');
  });

  it('returns the test answer in words without queuing it', async () => {
    const { relay } = make([{ outcome: 'wrong_key', status: 401 }]);
    const { result, words } = await relay.sendTest(settings, {
      from: 'TalNex test',
      body: 'hi',
      received_at: new Date(NOW).toISOString(),
      device: 'Spare',
    });
    expect(result.outcome).toBe('wrong_key');
    expect(words).toMatch(/Wrong key/);
    expect(relay.state().pending).toBe(0);
  });
});
