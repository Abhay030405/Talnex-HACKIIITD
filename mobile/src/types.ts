// Shapes shared by the relay. Nothing here touches React or native code.

/** The JSON body the server's POST /v1/sms/incoming expects. */
export interface GatewayPayload {
  from: string;
  body: string;
  received_at: string; // ISO 8601, UTC
  device: string;
}

/** What the person typed on the Settings screen. */
export interface Settings {
  gatewayUrl: string;
  gatewayKey: string;
  deviceName: string;
}

export type SendOutcome =
  | 'ok' // 200 or 202
  | 'wrong_key' // 401 or 403
  | 'rejected' // 400 or 413: the server will never take this message, so do not retry it
  | 'rate_limited' // 429: too many messages this minute, try again later
  | 'switched_off' // 503: the server has no gateway key set, so phone sign-up is off
  | 'server_error' // any other answer
  | 'not_set_up' // address or key missing, or the address is not an http(s) link
  | 'timeout' // no answer in time
  | 'unreachable'; // network error

export interface SendResult {
  outcome: SendOutcome;
  status?: number;
}

/** One line of the recent messages list. Never holds the message text. */
export interface HistoryEntry {
  id: string;
  from: string;
  receivedAt: string;
  status: 'sent' | 'failed';
  reason?: string;
}

/** A message waiting to be sent again. Removed once sent. */
export interface QueuedMessage {
  id: string;
  payload: GatewayPayload;
  attempts: number;
}

export interface IncomingSms {
  from: string;
  body: string;
  receivedAt: Date;
}

/** A tiny key-value store, so the logic runs in tests without a phone. */
export interface KeyValueStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}
