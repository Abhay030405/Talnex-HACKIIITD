import { AppState, PermissionsAndroid, Platform } from 'react-native';

import { relayServiceNative, type RelayServiceNative } from './native';

export const NOTICE_TITLE = 'TalNex SMS Relay is listening';
export const NOTICE_TEXT = 'Incoming texts are forwarded to TalNex. Turn listening off in the app to stop.';

/**
 * Keeps the app awake while listening is on, by showing a permanent notification (an Android foreground service).
 * Without it Android caches the app in the background and can kill it, and a killed app hears no texts.
 */
export interface KeepAlive {
  readonly supported: boolean;
  /** Returns a problem in words, or null once the notification is up. */
  start(): Promise<string | null>;
  stop(): void;
}

export interface KeepAliveDeps {
  native: Pick<RelayServiceNative, 'startService' | 'stopService'>;
  /** Asks for permission to show notifications. Without it the service still runs, only the notice is hidden. */
  askNotifications(): Promise<boolean>;
}

export function createKeepAliveWith(deps: KeepAliveDeps): KeepAlive {
  return {
    supported: true,
    async start() {
      try {
        await deps.askNotifications();
      } catch {
        // The notice is only hidden without the permission; keeping the app awake matters more.
      }
      try {
        deps.native.startService(NOTICE_TITLE, NOTICE_TEXT);
        return null;
      } catch (e) {
        return `Could not keep the app awake in the background: ${e instanceof Error ? e.message : String(e)}`;
      }
    },
    stop() {
      try {
        deps.native.stopService();
      } catch {
        // Already stopped.
      }
    },
  };
}

export function createUnsupportedKeepAlive(): KeepAlive {
  return { supported: false, start: async () => null, stop: () => {} };
}

export function createKeepAlive(): KeepAlive {
  const native = Platform.OS === 'android' ? relayServiceNative() : null;
  if (!native) return createUnsupportedKeepAlive();
  let asked = false;
  return createKeepAliveWith({
    native,
    askNotifications: async () => {
      // Android 12 and older show notifications without asking.
      if (Number(Platform.Version) < 33) return true;
      const permission = PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS;
      if (await PermissionsAndroid.check(permission)) return true;
      // Android can only show the question while the app is on screen. Ask once per start, not on every return.
      if (asked || AppState.currentState !== 'active') return false;
      asked = true;
      return (await PermissionsAndroid.request(permission)) === PermissionsAndroid.RESULTS.GRANTED;
    },
  });
}
