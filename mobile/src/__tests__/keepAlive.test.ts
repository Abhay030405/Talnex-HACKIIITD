import { NOTICE_TEXT, NOTICE_TITLE, createKeepAlive, createKeepAliveWith } from '../keepAlive';

function fakeNative(fail = false) {
  return {
    startService: jest.fn(() => {
      if (fail) throw new Error('not allowed from the background');
    }),
    stopService: jest.fn(),
  };
}

describe('keep-alive notification', () => {
  it('is not available without the native module (tests, Expo Go)', async () => {
    const k = createKeepAlive();
    expect(k.supported).toBe(false);
    expect(await k.start()).toBeNull();
  });

  it('asks for notifications, then starts the service with the notice', async () => {
    const native = fakeNative();
    const ask = jest.fn(async () => true);
    const k = createKeepAliveWith({ native, askNotifications: ask });
    expect(await k.start()).toBeNull();
    expect(ask).toHaveBeenCalled();
    expect(native.startService).toHaveBeenCalledWith(NOTICE_TITLE, NOTICE_TEXT);
  });

  it('still starts when notifications are refused', async () => {
    const native = fakeNative();
    const k = createKeepAliveWith({ native, askNotifications: async () => false });
    expect(await k.start()).toBeNull();
    expect(native.startService).toHaveBeenCalled();
  });

  it('still starts when asking for notifications fails (app not on screen)', async () => {
    const native = fakeNative();
    const k = createKeepAliveWith({
      native,
      askNotifications: async () => {
        throw new Error('Tried to use permissions API while not attached to an Activity.');
      },
    });
    expect(await k.start()).toBeNull();
    expect(native.startService).toHaveBeenCalled();
  });

  it('reports a service that could not start', async () => {
    const k = createKeepAliveWith({ native: fakeNative(true), askNotifications: async () => true });
    expect(await k.start()).toMatch(/not allowed from the background/);
  });

  it('stops quietly', () => {
    const native = fakeNative();
    native.stopService.mockImplementation(() => {
      throw new Error('not running');
    });
    const k = createKeepAliveWith({ native, askNotifications: async () => true });
    expect(() => k.stop()).not.toThrow();
  });
});
