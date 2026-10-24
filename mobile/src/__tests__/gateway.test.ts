import {
  describeResult,
  isRetryable,
  isValidGatewayUrl,
  normalizeGatewayUrl,
  outcomeForStatus,
  sendToGateway,
  settingsProblem,
  shortReason,
} from '../gateway';
import type { GatewayPayload, SendOutcome, Settings } from '../types';

const settings: Settings = {
  gatewayUrl: 'http://10.0.0.5:8080/v1/sms/incoming',
  gatewayKey: 'gateway-key-0123456789',
  deviceName: 'Spare',
};
const payload: GatewayPayload = {
  from: 'AX-BANK',
  body: 'code 1',
  received_at: '2026-01-01T00:00:00.000Z',
  device: 'Spare',
};

function recorder(status: number) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return { status };
  };
  return { calls, fetchImpl };
}

describe('addresses', () => {
  it('accepts http and https links only', () => {
    expect(isValidGatewayUrl('http://192.168.1.10:8080')).toBe(true);
    expect(isValidGatewayUrl(' https://talnex.example/v1/sms/incoming ')).toBe(true);
    expect(isValidGatewayUrl('192.168.1.10:8080')).toBe(false);
    expect(isValidGatewayUrl('ftp://x')).toBe(false);
    expect(isValidGatewayUrl('http://')).toBe(false);
  });

  it('adds the incoming path when only the server is typed', () => {
    expect(normalizeGatewayUrl('http://192.168.1.10:8080')).toBe('http://192.168.1.10:8080/v1/sms/incoming');
    expect(normalizeGatewayUrl('HTTP://host/')).toBe('http://host/v1/sms/incoming');
    expect(normalizeGatewayUrl('https://host/custom/path')).toBe('https://host/custom/path');
  });
});

describe('settingsProblem', () => {
  it('passes good settings', () => {
    expect(settingsProblem(settings)).toBeNull();
  });
  it.each([
    [{ gatewayUrl: '' }, /address/],
    [{ gatewayUrl: 'host:8080' }, /http/],
    [{ gatewayKey: '  ' }, /key/],
    [{ gatewayKey: 'short' }, /too short/],
  ])('explains %p', (change, words) => {
    expect(settingsProblem({ ...settings, ...change })).toMatch(words);
  });
});

describe('outcomeForStatus', () => {
  it.each<[number, SendOutcome]>([
    [200, 'ok'],
    [202, 'ok'],
    [401, 'wrong_key'],
    [403, 'wrong_key'],
    [400, 'rejected'],
    [413, 'rejected'],
    [429, 'rate_limited'],
    [503, 'switched_off'],
    [500, 'server_error'],
    [404, 'server_error'],
  ])('%i is %s', (status, outcome) => {
    expect(outcomeForStatus(status)).toBe(outcome);
  });

  it('retries everything except success and a refused message', () => {
    expect(isRetryable({ outcome: 'ok' })).toBe(false);
    expect(isRetryable({ outcome: 'rejected' })).toBe(false);
    expect(isRetryable({ outcome: 'rate_limited' })).toBe(true);
    expect(isRetryable({ outcome: 'unreachable' })).toBe(true);
    expect(isRetryable({ outcome: 'wrong_key' })).toBe(true);
  });
});

describe('sendToGateway', () => {
  it('posts JSON with the key header to the full address', async () => {
    const { calls, fetchImpl } = recorder(202);
    const result = await sendToGateway({ ...settings, gatewayUrl: 'http://10.0.0.5:8080' }, payload, fetchImpl);
    expect(result).toEqual({ outcome: 'ok', status: 202 });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('http://10.0.0.5:8080/v1/sms/incoming');
    expect(calls[0].init.method).toBe('POST');
    expect(calls[0].init.headers).toEqual({ 'Content-Type': 'application/json', 'X-Gateway-Key': settings.gatewayKey });
    expect(JSON.parse(calls[0].init.body as string)).toEqual(payload);
  });

  it('does not call the network when not set up', async () => {
    const { calls, fetchImpl } = recorder(202);
    expect((await sendToGateway({ ...settings, gatewayKey: '' }, payload, fetchImpl)).outcome).toBe('not_set_up');
    expect((await sendToGateway({ ...settings, gatewayUrl: 'nope' }, payload, fetchImpl)).outcome).toBe('not_set_up');
    expect(calls).toHaveLength(0);
  });

  it('turns a network error into unreachable', async () => {
    const fail = async () => {
      throw new Error('network down');
    };
    expect(await sendToGateway(settings, payload, fail)).toEqual({ outcome: 'unreachable' });
  });

  it('gives up after the timeout', async () => {
    const hang = (_url: string, init: RequestInit) =>
      new Promise<{ status: number }>((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
      });
    expect(await sendToGateway(settings, payload, hang, 20)).toEqual({ outcome: 'timeout' });
  });
});

describe('words', () => {
  const outcomes: SendOutcome[] = [
    'ok',
    'wrong_key',
    'rejected',
    'rate_limited',
    'switched_off',
    'server_error',
    'not_set_up',
    'timeout',
    'unreachable',
  ];

  it('has a sentence and a short reason for every outcome', () => {
    for (const outcome of outcomes) {
      expect(describeResult({ outcome }).length).toBeGreaterThan(10);
      expect(shortReason({ outcome }).length).toBeGreaterThan(0);
    }
  });

  it('includes the status code of a server error', () => {
    expect(describeResult({ outcome: 'server_error', status: 500 })).toContain('500');
    expect(shortReason({ outcome: 'server_error', status: 502 })).toBe('server error 502');
  });
});
