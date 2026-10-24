import { MAX_BODY_CHARS, MAX_FIELD_CHARS, buildPayload, buildTestPayload, clip, parseReadSmsString } from '../payload';

const at = new Date('2026-03-04T05:06:07Z');

describe('buildPayload', () => {
  it('builds exactly the four fields the server reads', () => {
    expect(buildPayload({ from: '+919800000000', body: 'Your code is 482913', receivedAt: at }, 'Team phone')).toEqual({
      from: '+919800000000',
      body: 'Your code is 482913',
      received_at: '2026-03-04T05:06:07.000Z',
      device: 'Team phone',
    });
  });

  it('cuts long fields to the server limits so the message is not refused', () => {
    const p = buildPayload({ from: 'x'.repeat(150), body: 'y'.repeat(1500), receivedAt: at }, 'd'.repeat(120));
    expect(p.from).toHaveLength(MAX_FIELD_CHARS);
    expect(p.body).toHaveLength(MAX_BODY_CHARS);
    expect(p.device).toHaveLength(MAX_FIELD_CHARS);
  });

  it('trims spaces around the sender and the phone name', () => {
    const p = buildPayload({ from: '  AX-BANK ', body: ' keep me ', receivedAt: at }, '  Spare  ');
    expect(p.from).toBe('AX-BANK');
    expect(p.device).toBe('Spare');
    expect(p.body).toBe(' keep me ');
  });

  it('builds the test message', () => {
    const p = buildTestPayload('Spare', at);
    expect(p).toMatchObject({ from: 'TalNex test', body: 'This is a test from the phone app', device: 'Spare' });
  });
});

describe('clip', () => {
  it('counts an emoji as one character and never splits it', () => {
    expect(clip('ab😀cd', 3)).toBe('ab😀');
    expect(clip('short', 10)).toBe('short');
  });
});

describe('parseReadSmsString', () => {
  it('splits on the first comma only', () => {
    expect(parseReadSmsString('[AX-BANK, Code 1, 2, 3. Do not share]', at)).toEqual({
      from: 'AX-BANK',
      body: 'Code 1, 2, 3. Do not share',
      receivedAt: at,
    });
  });

  it('keeps brackets inside the body', () => {
    expect(parseReadSmsString('[VM-OTP, use [482913] to sign in]')?.body).toBe('use [482913] to sign in');
  });

  it.each([['hello'], ['[]'], ['[only-sender]'], ['[null, null]'], ['[, body]'], [42], [null], [undefined]])(
    'returns null for %p',
    (raw) => {
      expect(parseReadSmsString(raw)).toBeNull();
    },
  );
});
