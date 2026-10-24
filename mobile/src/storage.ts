import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { isValidGatewayUrl, normalizeGatewayUrl } from './gateway';
import type { KeyValueStore, Settings } from './types';

/** Queue, history and the listening switch: plain on-device storage. */
export const deviceStore: KeyValueStore = {
  get: (k) => AsyncStorage.getItem(k),
  set: (k, v) => AsyncStorage.setItem(k, v),
  remove: (k) => AsyncStorage.removeItem(k),
};

const SECURE_KEYS = {
  url: 'talnex_gateway_url',
  key: 'talnex_gateway_key',
  device: 'talnex_device_name',
} as const;

export const DEFAULT_DEVICE_NAME = 'TalNex phone';
export const LISTENING_KEY = 'talnex.listening';

/** The address, key and phone name live in the phone's secure storage (Android Keystore). */
export async function loadSettings(): Promise<Settings> {
  const [url, key, device] = await Promise.all([
    SecureStore.getItemAsync(SECURE_KEYS.url),
    SecureStore.getItemAsync(SECURE_KEYS.key),
    SecureStore.getItemAsync(SECURE_KEYS.device),
  ]);
  return { gatewayUrl: url ?? '', gatewayKey: key ?? '', deviceName: device || DEFAULT_DEVICE_NAME };
}

/** Saves the settings trimmed, with the full incoming address filled in when only the server was typed. */
export async function saveSettings(s: Settings): Promise<Settings> {
  const url = s.gatewayUrl.trim();
  const clean: Settings = {
    gatewayUrl: isValidGatewayUrl(url) ? normalizeGatewayUrl(url) : url,
    gatewayKey: s.gatewayKey.trim(),
    deviceName: s.deviceName.trim() || DEFAULT_DEVICE_NAME,
  };
  await SecureStore.setItemAsync(SECURE_KEYS.url, clean.gatewayUrl);
  await SecureStore.setItemAsync(SECURE_KEYS.key, clean.gatewayKey);
  await SecureStore.setItemAsync(SECURE_KEYS.device, clean.deviceName);
  return clean;
}

export async function loadListening(): Promise<boolean> {
  return (await deviceStore.get(LISTENING_KEY)) === '1';
}

export async function saveListening(on: boolean): Promise<void> {
  await deviceStore.set(LISTENING_KEY, on ? '1' : '0');
}
