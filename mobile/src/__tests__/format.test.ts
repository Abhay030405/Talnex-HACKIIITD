import { entryStatus, formatWhen, waitingLine } from '../ui/format';

const NOW = Date.parse('2026-05-01T12:00:00Z');
const ago = (ms: number) => new Date(NOW - ms).toISOString();

describe('formatWhen', () => {
  it.each([
    [ago(10_000), 'just now'],
    [ago(5 * 60_000), '5 min ago'],
    [ago(59 * 60_000), '59 min ago'],
    [ago(3 * 3_600_000), '3 h ago'],
    ['nonsense', 'unknown time'],
  ])('%s is %s', (iso, words) => {
    expect(formatWhen(iso, NOW)).toBe(words);
  });

  it('shows a full date past a day', () => {
    expect(formatWhen(ago(2 * 86_400_000), NOW)).not.toMatch(/ago/);
  });
});

describe('entryStatus', () => {
  it('words each status', () => {
    expect(entryStatus({ id: '1', from: 'a', receivedAt: '', status: 'sent' })).toEqual({ text: 'sent', good: true });
    expect(entryStatus({ id: '1', from: 'a', receivedAt: '', status: 'failed', reason: 'wrong key' })).toEqual({
      text: 'failed: wrong key',
      good: false,
    });
    expect(entryStatus({ id: '1', from: 'a', receivedAt: '', status: 'failed' }).text).toBe('failed: unknown');
  });
});

describe('waitingLine', () => {
  it('counts in words', () => {
    expect(waitingLine(0)).toBe('Nothing waiting.');
    expect(waitingLine(1)).toBe('1 message waiting to be sent.');
    expect(waitingLine(4)).toBe('4 messages waiting to be sent.');
  });
});
