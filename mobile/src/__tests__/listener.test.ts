import {
  createAndroidListener,
  createSmsListener,
  createUnsupportedListener,
  NO_PERMISSION,
  UNSUPPORTED_NOTICE,
  type AndroidListenerDeps,
  type NativeSms,
} from '../sms/listener';
import type { IncomingSms } from '../types';

type NativeMode = 'ok' | 'fail' | 'silent' | 'throw';

function fakeAndroid(mode: NativeMode = 'ok', granted = true) {
  let handler: ((raw: unknown) => void) | null = null;
  const removed = jest.fn();
  const native: NativeSms & { stopReadSMS: jest.Mock } = {
    startReadSMS: (ok, fail) => {
      if (mode === 'ok') ok('Start Read SMS successfully');
      if (mode === 'fail') fail('Required RECEIVE_SMS and READ_SMS permission');
      if (mode === 'throw') throw new Error('native crash');
    },
    stopReadSMS: jest.fn(),
  };
  const deps: AndroidListenerDeps = {
    native,
    permissions: { check: async () => granted, request: async () => granted },
    onEvent: (h) => {
      handler = h;
      return { remove: removed };
    },
    startTimeoutMs: 20,
  };
  return { deps, native, removed, fire: (raw: unknown) => handler?.(raw), hasHandler: () => handler !== null };
}

describe('createUnsupportedListener', () => {
  it('explains itself and never starts', async () => {
    const l = createUnsupportedListener();
    expect(l.supported).toBe(false);
    expect(await l.start(() => {})).toBe(UNSUPPORTED_NOTICE);
    expect(await l.hasPermission()).toBe(false);
  });
});

describe('createSmsListener', () => {
  it('falls back to the unsupported listener when the native module is missing (tests, Expo Go)', () => {
    expect(createSmsListener().supported).toBe(false);
  });
});

describe('createAndroidListener', () => {
  it('passes each parsed text on and skips junk', async () => {
    const f = fakeAndroid();
    const got: IncomingSms[] = [];
    const l = createAndroidListener(f.deps);
    expect(await l.start((s) => got.push(s))).toBeNull();
    f.fire('[AX-BANK, Your code is 482913]');
    f.fire('garbage');
    expect(got).toHaveLength(1);
    expect(got[0]).toMatchObject({ from: 'AX-BANK', body: 'Your code is 482913' });
  });

  it('refuses to start without permission', async () => {
    const f = fakeAndroid('ok', false);
    expect(await createAndroidListener(f.deps).start(() => {})).toBe(NO_PERMISSION);
    expect(f.hasHandler()).toBe(false);
  });

  it.each<[NativeMode, RegExp]>([
    ['fail', /RECEIVE_SMS/],
    ['throw', /native crash/],
    ['silent', /did not start/],
  ])('reports a native start that ends in %s and cleans up', async (mode, words) => {
    const f = fakeAndroid(mode);
    expect(await createAndroidListener(f.deps).start(() => {})).toMatch(words);
    expect(f.removed).toHaveBeenCalled();
    expect(f.native.stopReadSMS).toHaveBeenCalled();
  });

  it('starts once and stops cleanly', async () => {
    const f = fakeAndroid();
    const l = createAndroidListener(f.deps);
    await l.start(() => {});
    expect(await l.start(() => {})).toBeNull();
    l.stop();
    l.stop();
    expect(f.native.stopReadSMS).toHaveBeenCalledTimes(1);
    expect(f.removed).toHaveBeenCalledTimes(1);
  });
});
