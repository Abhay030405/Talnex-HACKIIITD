/**
 * @jest-environment node
 */
import type { AddressInfo } from 'node:net';

import { sendToGateway } from '../gateway';
import { buildPayload, buildTestPayload } from '../payload';
import type { GatewayPayload, Settings } from '../types';
import { nodeFetch } from './nodeFetch';

interface MockGateway {
  server: import('node:http').Server;
  received: GatewayPayload[];
}
const { checkIncoming, createMockGateway } = require('../../scripts/mock-gateway') as {
  checkIncoming: (input: { key: string; gotKey?: string; rawBody: string; now?: number }) => { status: number };
  createMockGateway: (opts: { key: string }) => MockGateway;
};

const KEY = 'gateway-key-0123456789';
const now = Date.parse('2026-05-01T10:00:00Z');
const check = (body: unknown, gotKey = KEY) =>
  checkIncoming({ key: KEY, gotKey, rawBody: typeof body === 'string' ? body : JSON.stringify(body), now }).status;
const good = { from: 'ACME', body: 'Your code is 482913', received_at: '2026-05-01T09:59:00.000Z', device: 'phone1' };

describe('mock gateway rules', () => {
  it('matches the server answers', () => {
    expect(checkIncoming({ key: '', rawBody: JSON.stringify(good) }).status).toBe(503);
    expect(check(good, '')).toBe(401);
    expect(check(good, 'gateway-key-wrong-00000')).toBe(401);
    expect(check(good)).toBe(202);
    expect(check('nope')).toBe(400);
    expect(check({ ...good, body: '' })).toBe(400);
    expect(check({ ...good, from: '' })).toBe(400);
    expect(check({ ...good, received_at: 'yesterday' })).toBe(400);
    expect(check({ ...good, received_at: '2026-05-01T11:00:00Z' })).toBe(400);
    expect(check({ ...good, body: 'a'.repeat(1001) })).toBe(400);
    expect(check({ ...good, body: 'a'.repeat(1000) })).toBe(202);
    expect(check({ ...good, body: 'a'.repeat(9000) })).toBe(400);
  });

  it('accepts every payload the app builds, even an over-long text', () => {
    const at = new Date(now - 1000);
    expect(
      check(buildPayload({ from: 'x'.repeat(300), body: '😀'.repeat(1200), receivedAt: at }, 'd'.repeat(300))),
    ).toBe(202);
    expect(check(buildTestPayload('Spare', at))).toBe(202);
  });
});

describe('the app against the mock over real HTTP', () => {
  let mock: MockGateway;
  let settings: Settings;

  beforeAll(async () => {
    mock = createMockGateway({ key: KEY });
    await new Promise<void>((resolve) => mock.server.listen(0, '127.0.0.1', resolve));
    const { port } = mock.server.address() as AddressInfo;
    settings = { gatewayUrl: `http://127.0.0.1:${port}`, gatewayKey: KEY, deviceName: 'Spare' };
  });

  afterAll(async () => {
    await new Promise((resolve) => mock.server.close(resolve));
  });

  it('delivers a message', async () => {
    const payload = buildTestPayload('Spare');
    expect(await sendToGateway(settings, payload, nodeFetch)).toEqual({ outcome: 'ok', status: 202 });
    expect(mock.received).toContainEqual(payload);
  });

  it('reports a wrong key', async () => {
    const result = await sendToGateway(
      { ...settings, gatewayKey: 'gateway-key-wrong-00000' },
      buildTestPayload('Spare'),
      nodeFetch,
    );
    expect(result).toEqual({ outcome: 'wrong_key', status: 401 });
  });

  it('reports a refused message', async () => {
    const future = buildTestPayload('Spare', new Date(Date.now() + 60 * 60 * 1000));
    expect(await sendToGateway(settings, future, nodeFetch)).toEqual({ outcome: 'rejected', status: 400 });
  });

  it('reports a closed port as unreachable', async () => {
    expect(
      await sendToGateway({ ...settings, gatewayUrl: 'http://127.0.0.1:1' }, buildTestPayload('Spare'), nodeFetch),
    ).toEqual({
      outcome: 'unreachable',
    });
  });
});
