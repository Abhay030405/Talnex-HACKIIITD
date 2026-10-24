import * as Network from 'expo-network';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';

import { CatchUp } from './src/catchUp';
import { sendToGateway } from './src/gateway';
import { emptyHistory } from './src/history';
import { createKeepAlive } from './src/keepAlive';
import { Relay, type RelayState } from './src/relay';
import { createSmsListener } from './src/sms/listener';
import { deviceStore, loadListening, loadSettings, saveListening, saveSettings } from './src/storage';
import type { IncomingSms, Settings } from './src/types';
import { SettingsScreen } from './src/ui/SettingsScreen';
import { StatusScreen } from './src/ui/StatusScreen';
import { colors, font, radius, space } from './src/ui/theme';

const RETRY_EVERY_MS = 60_000;
const TABS = [
  { id: 'status', label: 'Status' },
  { id: 'settings', label: 'Settings' },
] as const;
type Tab = (typeof TABS)[number]['id'];

// One of each per app process, not per screen: with the app running in the background, Android can destroy and
// rebuild the screen while the process (and the listener) lives on.
let currentSettings: Settings | null = null;
const listener = createSmsListener();
const keepAlive = createKeepAlive();
const relay = new Relay({
  store: deviceStore,
  getSettings: async () => currentSettings ?? (await loadSettings()),
  send: (s, p) => sendToGateway(s, p),
});
const catchUp = new CatchUp({
  store: deviceStore,
  readInbox: (sinceMs) => listener.readInboxSince(sinceMs),
  forward: (sms) => relay.handleIncoming(sms),
});
let loading: Promise<void> | null = null;
const loadOnce = () => (loading ??= Promise.all([relay.load(), catchUp.load()]).then(() => undefined));

function onSms(sms: IncomingSms) {
  catchUp.noteLive(sms);
  void relay.handleIncoming(sms);
}

/** Sends texts that arrived while the app was not running, then the ones waiting for the server. */
async function catchUpAndRetry() {
  try {
    await catchUp.run();
    await relay.retryPending();
  } catch (e) {
    console.warn('catch-up failed', e instanceof Error ? e.stack : e);
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('status');
  const [settings, setSettings] = useState<Settings | null>(null);
  const [listening, setListening] = useState(false);
  const [state, setState] = useState<RelayState>({ history: emptyHistory, pending: 0 });

  const startListening = useCallback(async (): Promise<string | null> => {
    if (!listener.supported) return listener.notice;
    if (!(await listener.hasPermission()) && !(await listener.requestPermission())) {
      return 'Permission was not given. Without it the app cannot see incoming texts.';
    }
    const problem = await listener.start(onSms);
    if (problem) return problem;
    await catchUp.begin();
    await saveListening(true);
    setListening(true);
    return keepAlive.start();
  }, []);

  const onToggle = useCallback(
    async (on: boolean): Promise<string | null> => {
      if (on) return startListening();
      listener.stop();
      keepAlive.stop();
      await catchUp.end();
      await saveListening(false);
      setListening(false);
      return null;
    },
    [startListening],
  );

  // Start-up: load what was saved, turn listening back on if it was on, then send anything missed or waiting.
  // The listener is not stopped when the screen goes away: it belongs to the process, not the screen.
  useEffect(() => {
    const unsubscribe = relay.subscribe(setState);
    void (async () => {
      const saved = await loadSettings();
      currentSettings = saved;
      setSettings(saved);
      await loadOnce();
      if (listener.supported && (await loadListening()) && (await listener.hasPermission())) {
        await startListening();
      }
      await catchUpAndRetry();
    })();
    return unsubscribe;
  }, [startListening]);

  // Also when the app comes back, when the connection returns, and every minute. Coming back also puts the
  // listening notice up again, in case it could not start while the phone was locked.
  useEffect(() => {
    const run = () => void catchUpAndRetry();
    const appSub = AppState.addEventListener('change', (s) => {
      if (s !== 'active') return;
      void loadListening().then((on) => (on ? keepAlive.start() : null));
      run();
    });
    const netSub = Network.addNetworkStateListener((n) => n.isConnected && run());
    const timer = setInterval(run, RETRY_EVERY_MS);
    return () => {
      appSub.remove();
      netSub.remove();
      clearInterval(timer);
    };
  }, []);

  const onSave = useCallback(async (typed: Settings) => {
    const saved = await saveSettings(typed);
    currentSettings = saved;
    setSettings(saved);
    void relay.retryPending();
  }, []);

  if (!settings) return <View style={styles.root} />;

  return (
    <View style={styles.root}>
      <StatusBar style="light" />
      <Text style={styles.title}>TalNex SMS Relay</Text>
      <View style={styles.tabs}>
        {TABS.map((t) => (
          <Pressable key={t.id} style={[styles.tab, tab === t.id && styles.tabOn]} onPress={() => setTab(t.id)}>
            <Text style={styles.tabText}>{t.label}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.flex}>
        {tab === 'status' ? (
          <StatusScreen
            relay={relay}
            listener={listener}
            settings={settings}
            state={state}
            listening={listening}
            onToggle={onToggle}
          />
        ) : (
          <SettingsScreen
            key={`${settings.gatewayUrl}|${settings.deviceName}`}
            relay={relay}
            settings={settings}
            onSave={onSave}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, paddingTop: space.xl },
  flex: { flex: 1 },
  title: {
    color: colors.text,
    fontSize: font.title,
    fontWeight: '700',
    paddingHorizontal: space.m,
    paddingBottom: space.s,
  },
  tabs: { flexDirection: 'row', paddingHorizontal: space.m, gap: space.s },
  tab: {
    paddingVertical: space.s,
    paddingHorizontal: space.m,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
  },
  tabOn: { backgroundColor: colors.accent },
  tabText: { color: colors.onAccent, fontWeight: '600' },
});
