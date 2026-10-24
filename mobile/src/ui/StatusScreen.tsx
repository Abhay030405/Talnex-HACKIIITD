import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { MAX_HISTORY } from '../history';
import type { Relay, RelayState } from '../relay';
import type { SmsListener } from '../sms/listener';
import type { Settings } from '../types';
import { entryStatus, formatWhen, waitingLine } from './format';
import { colors, font, radius, space } from './theme';

interface Props {
  relay: Relay;
  listener: SmsListener;
  settings: Settings;
  state: RelayState;
  listening: boolean;
  onToggle: (on: boolean) => Promise<string | null>;
}

export function StatusScreen({ relay, listener, settings, state, listening, onToggle }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permitted, setPermitted] = useState<boolean | null>(null);
  const [retryWords, setRetryWords] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (listener.supported) void listener.hasPermission().then(setPermitted);
  }, [listener, listening]);

  // Keeps "5 min ago" honest while the screen stays open.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const toggle = async (on: boolean) => {
    setBusy(true);
    setError(null);
    setError(await onToggle(on));
    setBusy(false);
  };

  const retryNow = async () => {
    setRetryWords('Sending...');
    const r = await relay.retryPending();
    setRetryWords(`Sent ${r.sent}. Still waiting: ${r.left}.`);
  };

  const { entries, sentCount } = state.history;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      {!listener.supported && (
        <View style={[styles.card, styles.warnCard]}>
          <Text style={styles.warnText}>{listener.notice}</Text>
        </View>
      )}

      <View style={styles.card}>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.big}>SMS listening: {listening ? 'ON' : 'OFF'}</Text>
            <Text style={styles.muted}>
              {listening
                ? 'New texts to this SIM are sent to TalNex. Texts that arrive while the app is closed are sent when it opens again.'
                : 'Texts are not being forwarded.'}
            </Text>
          </View>
          <Switch
            value={listening}
            disabled={busy || !listener.supported}
            onValueChange={toggle}
            trackColor={{ true: colors.good, false: colors.border }}
            style={styles.bigSwitch}
          />
        </View>
        {listener.supported && permitted === false && (
          <Text style={styles.muted}>
            Why the app asks for SMS permission: it must see the texts this SIM receives, like sign-up codes, to pass
            them to TalNex. It never sends texts and reads nothing else.
          </Text>
        )}
        {error && <Text style={styles.error}>{error}</Text>}
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>Server address</Text>
        <Text style={styles.value}>{settings.gatewayUrl || 'Not set. Open Settings.'}</Text>
        <View style={styles.counters}>
          <View>
            <Text style={styles.big}>{sentCount}</Text>
            <Text style={styles.muted}>sent</Text>
          </View>
          <View>
            <Text style={[styles.big, state.pending > 0 && styles.warnNumber]}>{state.pending}</Text>
            <Text style={styles.muted}>waiting</Text>
          </View>
        </View>
        <Text style={styles.muted}>{waitingLine(state.pending)}</Text>
        {state.pending > 0 && (
          <Pressable style={styles.button} onPress={retryNow}>
            <Text style={styles.buttonText}>Try waiting messages now</Text>
          </Pressable>
        )}
        {retryWords && <Text style={styles.muted}>{retryWords}</Text>}
      </View>

      <Text style={styles.heading}>Last {MAX_HISTORY} messages</Text>
      {entries.length === 0 && <Text style={styles.muted}>Nothing yet.</Text>}
      {entries.map((e) => {
        const status = entryStatus(e);
        return (
          <View key={e.id} style={styles.item}>
            <View style={styles.flex}>
              <Text style={styles.value}>{e.from}</Text>
              <Text style={styles.muted}>{formatWhen(e.receivedAt, now)}</Text>
            </View>
            <Text style={[styles.status, { color: status.good ? colors.good : colors.bad }]}>{status.text}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.m, gap: space.m },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.m,
    padding: space.m,
    gap: space.s,
    borderColor: colors.border,
    borderWidth: 1,
  },
  warnCard: { borderColor: colors.warn },
  warnText: { color: colors.warn, fontSize: font.body },
  warnNumber: { color: colors.warn },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.m },
  flex: { flex: 1 },
  big: { color: colors.text, fontSize: font.big, fontWeight: '700' },
  bigSwitch: { transform: [{ scaleX: 1.4 }, { scaleY: 1.4 }] },
  muted: { color: colors.muted, fontSize: font.body },
  label: { color: colors.muted, fontSize: font.small },
  value: { color: colors.text, fontSize: font.value },
  counters: { flexDirection: 'row', gap: space.xl, marginTop: space.s },
  heading: { color: colors.text, fontSize: font.heading, fontWeight: '600', marginTop: space.s },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s,
    backgroundColor: colors.card,
    borderRadius: radius.s,
    padding: space.m,
  },
  status: { fontSize: font.body, flexShrink: 1, textAlign: 'right' },
  error: { color: colors.bad, fontSize: font.body },
  button: { backgroundColor: colors.accent, borderRadius: radius.s, padding: space.m - space.xs, alignItems: 'center' },
  buttonText: { color: colors.onAccent, fontWeight: '600' },
});
