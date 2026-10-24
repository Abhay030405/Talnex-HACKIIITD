import * as Network from 'expo-network';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';

import { sendToGateway } from './src/gateway';
import { emptyHistory } from './src/history';
import { Relay, type RelayState } from './src/relay';
import { createSmsListener } from './src/sms/listener';
import { deviceStore, loadListening, loadSettings, saveListening, saveSettings } from './src/storage';
import type { Settings } from './src/types';
import { SettingsScreen } from './src/ui/SettingsScreen';
import { StatusScreen } from './src/ui/StatusScreen';
import { colors, font, radius, space } from './src/ui/theme';

const RETRY_EVERY_MS = 60_000;
const TABS = [
  { id: 'status', label: 'Status' },
  { id: 'settings', label: 'Settings' },
] as const;
type Tab = (typeof TABS)[number]['id'];

export default function App() {
  const [tab, setTab] = useState<Tab>('status');
  const [settings, setSettings] = useState<Settings | null>(null);
  const [listening, setListening] = useState(false);
  const [state, setState] = useState<RelayState>({ history: emptyHistory, pending: 0 });

  // The relay reads settings through this ref, so a text arriving right after Save uses the new values.
  const settingsRef = useRef<Settings | null>(null);
  const listener = useMemo(() => createSmsListener(), []);
  const relay = useMemo(
    () =>
      new Relay({
        store: deviceStore,
        getSettings: async () => settingsRef.current ?? (await loadSettings()),
        send: (s, p) => sendToGateway(s, p),
      }),
    [],
  );

  const startListening = useCallback(async (): Promise<string | null> => {
    if (!listener.supported) return listener.notice;
    if (!(await listener.hasPermission()) && !(await listener.requestPermission())) {
      return 'Permission was not given. Without it the app cannot see incoming texts.';
    }
    const problem = await listener.start((sms) => void relay.handleIncoming(sms));
    if (problem) return problem;
    setListening(true);
    await saveListening(true);
    return null;
  }, [listener, relay]);

  const onToggle = useCallback(
    async (on: boolean): Promise<string | null> => {
      if (on) return startListening();
      listener.stop();
      setListening(false);
      await saveListening(false);
      return null;
    },
    [listener, startListening],
  );

  // Start-up: load what was saved, turn listening back on if it was on, then try anything waiting.
  useEffect(() => {
    const unsubscribe = relay.subscribe(setState);
    void (async () => {
      const saved = await loadSettings();
      settingsRef.current = saved;
      setSettings(saved);
      await relay.load();
      if (listener.supported && (await loadListening()) && (await listener.hasPermission())) {
        await startListening();
      }
      await relay.retryPending();
    })();
    return () => {
      unsubscribe();
      listener.stop();
    };
  }, [relay, listener, startListening]);

  // Waiting messages are tried again when the app comes back, when the connection returns, and every minute.
  useEffect(() => {
    const retry = () => void relay.retryPending();
    const appSub = AppState.addEventListener('change', (s) => s === 'active' && retry());
    const netSub = Network.addNetworkStateListener((n) => n.isConnected && retry());
    const timer = setInterval(retry, RETRY_EVERY_MS);
    return () => {
      appSub.remove();
      netSub.remove();
      clearInterval(timer);
    };
  }, [relay]);

  const onSave = useCallback(
    async (typed: Settings) => {
      const saved = await saveSettings(typed);
      settingsRef.current = saved;
      setSettings(saved);
      void relay.retryPending();
    },
    [relay],
  );

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
