import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { DEFAULT_DEVICE_NAME, loadListening, loadSettings, saveListening, saveSettings } from '../storage';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-secure-store', () => {
  const data = new Map<string, string>();
  return {
    __data: data,
    getItemAsync: jest.fn(async (k: string) => data.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => {
      data.set(k, v);
    }),
  };
});

const secureData = (SecureStore as unknown as { __data: Map<string, string> }).__data;

beforeEach(async () => {
  secureData.clear();
  await AsyncStorage.clear();
});

describe('settings', () => {
  it('starts empty with a default phone name', async () => {
    expect(await loadSettings()).toEqual({ gatewayUrl: '', gatewayKey: '', deviceName: DEFAULT_DEVICE_NAME });
  });

  it('saves trimmed values with the full address, in secure storage only', async () => {
    const saved = await saveSettings({
      gatewayUrl: ' http://192.168.1.10:8080 ',
      gatewayKey: ' gateway-key-0123456789 ',
      deviceName: '  ',
    });
    expect(saved).toEqual({
      gatewayUrl: 'http://192.168.1.10:8080/v1/sms/incoming',
      gatewayKey: 'gateway-key-0123456789',
      deviceName: DEFAULT_DEVICE_NAME,
    });
    expect(await loadSettings()).toEqual(saved);
    expect(await AsyncStorage.getAllKeys()).toEqual([]);
  });

  it('keeps an address it cannot understand as typed, so the person can fix it', async () => {
    const saved = await saveSettings({ gatewayUrl: '192.168.1.10', gatewayKey: 'k', deviceName: 'Spare' });
    expect(saved.gatewayUrl).toBe('192.168.1.10');
  });
});

describe('listening switch', () => {
  it('is off until turned on, and remembered', async () => {
    expect(await loadListening()).toBe(false);
    await saveListening(true);
    expect(await loadListening()).toBe(true);
    await saveListening(false);
    expect(await loadListening()).toBe(false);
  });
});
