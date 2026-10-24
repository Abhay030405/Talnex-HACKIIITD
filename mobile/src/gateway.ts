import type { GatewayPayload, SendOutcome, SendResult, Settings } from './types';

export const SEND_TIMEOUT_MS = 10_000;
export const GATEWAY_PATH = '/v1/sms/incoming';
// The server switches phone sign-up off when its key is shorter than this.
export const MIN_KEY_LENGTH = 16;

type FetchLike = (url: string, init: RequestInit) => Promise<{ status: number }>;

const URL_SHAPE = /^(https?):\/\/([^\s/?#]+)([^\s?#]*)$/i;

export function isValidGatewayUrl(url: string): boolean {
  return URL_SHAPE.test(url.trim());
}

/**
 * People often type just the server, like "http://192.168.1.10:8080".
 * When no path is given, the incoming SMS path is added; a typed path is kept as it is.
 */
export function normalizeGatewayUrl(url: string): string {
  const match = URL_SHAPE.exec(url.trim());
  if (!match) return url.trim();
  const [, scheme, host, path] = match;
  const cleanPath = path === '' || path === '/' ? GATEWAY_PATH : path;
  return `${scheme.toLowerCase()}://${host}${cleanPath}`;
}

/** What is wrong with the typed settings, in words, or null when they look usable. */
export function settingsProblem(s: Settings): string | null {
  if (!s.gatewayUrl.trim()) return 'Type the server address.';
  if (!isValidGatewayUrl(s.gatewayUrl)) return 'The address must start with http:// or https://.';
  if (!s.gatewayKey.trim()) return 'Type the key.';
  if (s.gatewayKey.trim().length < MIN_KEY_LENGTH) {
    return `The key is too short. The server needs at least ${MIN_KEY_LENGTH} characters.`;
  }
  return null;
}

export function outcomeForStatus(status: number): SendOutcome {
  if (status === 200 || status === 202) return 'ok';
  if (status === 401 || status === 403) return 'wrong_key';
  if (status === 400 || status === 413) return 'rejected';
  if (status === 429) return 'rate_limited';
  if (status === 503) return 'switched_off';
  return 'server_error';
}

/** A message that failed this way may get through later. A rejected one never will. */
export function isRetryable(result: SendResult): boolean {
  return result.outcome !== 'ok' && result.outcome !== 'rejected';
}

/**
 * Sends one message. Never throws: every problem comes back as an outcome.
 * The key goes only into the header. It is never logged or returned.
 */
export async function sendToGateway(
  settings: Settings,
  payload: GatewayPayload,
  fetchImpl: FetchLike = fetch as unknown as FetchLike,
  timeoutMs: number = SEND_TIMEOUT_MS,
): Promise<SendResult> {
  const key = settings.gatewayKey.trim();
  if (!key || !isValidGatewayUrl(settings.gatewayUrl)) return { outcome: 'not_set_up' };

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const res = await fetchImpl(normalizeGatewayUrl(settings.gatewayUrl), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gateway-Key': key },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    return { outcome: outcomeForStatus(res.status), status: res.status };
  } catch {
    return { outcome: timedOut ? 'timeout' : 'unreachable' };
  } finally {
    clearTimeout(timer);
  }
}

/** The answer in a full sentence, for the Settings screen. */
export function describeResult(result: SendResult): string {
  switch (result.outcome) {
    case 'ok':
      return 'Works. The server accepted the message.';
    case 'wrong_key':
      return 'Wrong key. The server refused it. Check the key in Settings.';
    case 'rejected':
      return 'The server refused this message as invalid. It will not be sent again.';
    case 'rate_limited':
      return 'The server is getting too many messages right now. It will be sent again shortly.';
    case 'switched_off':
      return 'Phone sign-up is switched off on the server (no gateway key is set there).';
    case 'server_error':
      return `The server answered with an error (code ${result.status ?? 'unknown'}).`;
    case 'not_set_up':
      return 'Not set up. Type the server address (starting with http:// or https://) and the key in Settings.';
    case 'timeout':
      return 'Cannot reach the server. It did not answer in time.';
    case 'unreachable':
      return 'Cannot reach the server. Check the address and that the phone and server are on the same network.';
  }
}

/** A few words, for the recent messages list. */
export function shortReason(result: SendResult): string {
  switch (result.outcome) {
    case 'ok':
      return 'sent';
    case 'wrong_key':
      return 'wrong key';
    case 'rejected':
      return 'refused by server';
    case 'rate_limited':
      return 'server busy';
    case 'switched_off':
      return 'switched off on server';
    case 'server_error':
      return result.status ? `server error ${result.status}` : 'server error';
    case 'not_set_up':
      return 'not set up';
    case 'timeout':
      return 'server too slow';
    case 'unreachable':
      return 'cannot reach server';
  }
}
