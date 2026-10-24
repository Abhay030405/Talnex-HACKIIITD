import { requireOptionalNativeModule } from 'expo';

/** One text from the phone's SMS inbox. `date` is when the phone received it, in milliseconds. */
export interface InboxRow {
  id: string;
  from: string;
  body: string;
  date: number;
}

/** The app's own native module in modules/relay-service. Missing in Expo Go, on iOS and in tests. */
export interface RelayServiceNative {
  startService(title: string, text: string): void;
  stopService(): void;
  isServiceRunning(): boolean;
  readInboxSince(sinceMs: number, limit: number): Promise<InboxRow[]>;
}

export function relayServiceNative(): RelayServiceNative | null {
  return requireOptionalNativeModule<RelayServiceNative>('RelayService');
}
