import type { GatewayPayload, IncomingSms } from './types';

// The server refuses anything longer than these, counted in characters, not bytes.
export const MAX_BODY_CHARS = 1000;
export const MAX_FIELD_CHARS = 100;

export const TEST_SENDER = 'TalNex test';
export const TEST_BODY = 'This is a test from the phone app';

/** Cuts a string to at most `max` characters without splitting an emoji or other surrogate pair. */
export function clip(text: string, max: number): string {
  const chars = Array.from(text);
  return chars.length <= max ? text : chars.slice(0, max).join('');
}

/**
 * The body the server expects. Long texts are cut to the server's limit instead of being refused:
 * a sign-up code sits near the start of a message, so the start is the part worth keeping.
 */
export function buildPayload(sms: IncomingSms, device: string): GatewayPayload {
  return {
    from: clip(sms.from.trim(), MAX_FIELD_CHARS),
    body: clip(sms.body, MAX_BODY_CHARS),
    received_at: sms.receivedAt.toISOString(),
    device: clip(device.trim(), MAX_FIELD_CHARS),
  };
}

export function buildTestPayload(device: string, now: Date = new Date()): GatewayPayload {
  return buildPayload({ from: TEST_SENDER, body: TEST_BODY, receivedAt: now }, device);
}

/**
 * The SMS library sends each message as one string shaped like "[sender, body]".
 * The body can hold commas, so only the first ", " separates the two.
 */
export function parseReadSmsString(raw: unknown, receivedAt: Date = new Date()): IncomingSms | null {
  if (typeof raw !== 'string') return null;
  const text = raw.trim();
  if (text.length < 2 || text[0] !== '[' || text[text.length - 1] !== ']') return null;
  const inner = text.slice(1, -1);
  const comma = inner.indexOf(', ');
  if (comma <= 0) return null;
  const from = inner.slice(0, comma).trim();
  const body = inner.slice(comma + 2);
  if (!from || from === 'null' || !body || body === 'null') return null;
  return { from, body, receivedAt };
}
