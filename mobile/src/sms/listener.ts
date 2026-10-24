import { DeviceEventEmitter, NativeModules, PermissionsAndroid, Platform } from 'react-native';

import { parseReadSmsString } from '../payload';
import type { IncomingSms } from '../types';

/**
 * Everything the rest of the app knows about SMS listening. This file is the only SMS code:
 * replacing the library later means changing only this file.
 */
export interface SmsListener {
  /** false in Expo Go and on iOS, where there is no SMS module. */
  readonly supported: boolean;
  /** Shown in words when listening is not supported. */
  readonly notice: string;
  hasPermission(): Promise<boolean>;
  /** Asks Android for the SMS permission. True when it was given. */
  requestPermission(): Promise<boolean>;
  /** Starts listening. Returns a problem in words, or null once it is running. */
  start(onSms: (sms: IncomingSms) => void): Promise<string | null>;
  stop(): void;
}

export const UNSUPPORTED_NOTICE =
  'SMS listening needs the Android development build; the rest of the app works for testing.';
export const NO_PERMISSION = 'The SMS permission is not allowed yet.';
export const START_TIMEOUT_MS = 5_000;

export function createUnsupportedListener(): SmsListener {
  return {
    supported: false,
    notice: UNSUPPORTED_NOTICE,
    hasPermission: async () => false,
    requestPermission: async () => false,
    start: async () => UNSUPPORTED_NOTICE,
    stop: () => {},
  };
}

/** The native side of @maniac-tech/react-native-expo-read-sms. Its JS helpers are skipped on purpose. */
export interface NativeSms {
  startReadSMS(ok: (message: string) => void, fail: (error: string) => void): void;
  stopReadSMS(): void;
}

export interface AndroidListenerDeps {
  native: NativeSms;
  permissions: {
    check(): Promise<boolean>;
    request(): Promise<boolean>;
  };
  /** Subscribes to the library's "received_sms" event. */
  onEvent(handler: (raw: unknown) => void): { remove(): void };
  startTimeoutMs?: number;
}

export function createAndroidListener(deps: AndroidListenerDeps): SmsListener {
  let subscription: { remove(): void } | null = null;
  let running = false;

  const unsubscribe = () => {
    subscription?.remove();
    subscription = null;
  };

  return {
    supported: true,
    notice: '',
    hasPermission: () => deps.permissions.check(),
    requestPermission: () => deps.permissions.request(),

    async start(onSms) {
      if (running) return null;
      if (!(await deps.permissions.check())) return NO_PERMISSION;

      // Listen for the event before the receiver is switched on, so the first text is not missed.
      unsubscribe();
      subscription = deps.onEvent((raw) => {
        const sms = parseReadSmsString(raw);
        if (sms) onSms(sms);
      });

      // The library calls neither callback when it hits an error inside, so do not wait forever.
      const problem = await new Promise<string | null>((resolve) => {
        const timer = setTimeout(
          () => resolve('The SMS listener did not start. Close and reopen the app.'),
          deps.startTimeoutMs ?? START_TIMEOUT_MS,
        );
        const done = (value: string | null) => {
          clearTimeout(timer);
          resolve(value);
        };
        try {
          deps.native.startReadSMS(
            () => done(null),
            (e) => done(String(e) || 'The SMS listener did not start.'),
          );
        } catch (e) {
          done(e instanceof Error ? e.message : String(e));
        }
      });

      if (problem) {
        unsubscribe();
        deps.native.stopReadSMS();
        return problem;
      }
      running = true;
      return null;
    },

    stop() {
      unsubscribe();
      if (running) deps.native.stopReadSMS();
      running = false;
    },
  };
}

const SMS_PERMISSIONS = [PermissionsAndroid.PERMISSIONS.RECEIVE_SMS, PermissionsAndroid.PERMISSIONS.READ_SMS];

/** The real listener when this build has the SMS module, otherwise the one that does nothing. */
export function createSmsListener(): SmsListener {
  if (Platform.OS !== 'android') return createUnsupportedListener();
  const native = NativeModules.RNExpoReadSms as NativeSms | undefined;
  if (!native || typeof native.startReadSMS !== 'function') return createUnsupportedListener();

  return createAndroidListener({
    native,
    permissions: {
      check: async () => (await Promise.all(SMS_PERMISSIONS.map((p) => PermissionsAndroid.check(p)))).every(Boolean),
      request: async () => {
        const result = await PermissionsAndroid.requestMultiple(SMS_PERMISSIONS);
        return SMS_PERMISSIONS.every((p) => result[p] === PermissionsAndroid.RESULTS.GRANTED);
      },
    },
    onEvent: (handler) => DeviceEventEmitter.addListener('received_sms', handler),
  });
}
