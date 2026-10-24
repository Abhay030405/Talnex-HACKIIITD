import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { isValidGatewayUrl, normalizeGatewayUrl, settingsProblem } from '../gateway';
import { MAX_FIELD_CHARS, buildTestPayload } from '../payload';
import type { Relay } from '../relay';
import { DEFAULT_DEVICE_NAME } from '../storage';
import type { Settings } from '../types';
import { colors, font, radius, space } from './theme';

interface Props {
  relay: Relay;
  settings: Settings;
  onSave: (s: Settings) => Promise<void>;
}

type Notice = { text: string; good: boolean };

export function SettingsScreen({ relay, settings, onSave }: Props) {
  const [url, setUrl] = useState(settings.gatewayUrl);
  const [key, setKey] = useState(settings.gatewayKey);
  const [device, setDevice] = useState(settings.deviceName);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<'save' | 'test' | null>(null);

  const draft: Settings = { gatewayUrl: url, gatewayKey: key, deviceName: device };
  const problem = settingsProblem(draft);
  const fullUrl = isValidGatewayUrl(url) ? normalizeGatewayUrl(url) : null;

  const save = async () => {
    setBusy('save');
    await onSave(draft);
    setNotice(problem ? { text: `Saved, but: ${problem}`, good: false } : { text: 'Saved on this phone.', good: true });
    setBusy(null);
  };

  const test = async () => {
    setBusy('test');
    setNotice(null);
    const { result, words } = await relay.sendTest(draft, buildTestPayload(device.trim() || DEFAULT_DEVICE_NAME));
    setNotice({ text: words, good: result.outcome === 'ok' });
    setBusy(null);
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Text style={styles.label}>Server address</Text>
      <TextInput
        style={styles.input}
        value={url}
        onChangeText={setUrl}
        placeholder="http://192.168.1.10:8080"
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />
      {fullUrl && fullUrl !== url.trim() && <Text style={styles.hint}>Texts will go to {fullUrl}</Text>}

      <Text style={styles.label}>Key (the SMS_GATEWAY_KEY set on the server)</Text>
      <TextInput
        style={styles.input}
        value={key}
        onChangeText={setKey}
        secureTextEntry
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="secret key"
        placeholderTextColor={colors.muted}
      />

      <Text style={styles.label}>This phone's name</Text>
      <TextInput
        style={styles.input}
        value={device}
        onChangeText={setDevice}
        maxLength={MAX_FIELD_CHARS}
        placeholder={DEFAULT_DEVICE_NAME}
        placeholderTextColor={colors.muted}
      />

      {problem && <Text style={styles.warn}>{problem}</Text>}

      <Pressable style={[styles.button, busy !== null && styles.dim]} onPress={save} disabled={busy !== null}>
        <Text style={styles.buttonText}>{busy === 'save' ? 'Saving...' : 'Save'}</Text>
      </Pressable>
      <Pressable
        style={[styles.button, styles.secondary, (busy !== null || problem !== null) && styles.dim]}
        onPress={test}
        disabled={busy !== null || problem !== null}
      >
        <Text style={styles.buttonText}>{busy === 'test' ? 'Sending...' : 'Send test message'}</Text>
      </Pressable>

      {notice && (
        <View style={styles.card}>
          <Text style={[styles.notice, { color: notice.good ? colors.good : colors.bad }]}>{notice.text}</Text>
        </View>
      )}
      <Text style={styles.hint}>
        The test uses the values typed above, saved or not. It comes from "TalNex test" and is not counted as a real
        message.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.m, gap: space.s },
  label: { color: colors.muted, fontSize: font.small, marginTop: space.s },
  input: {
    backgroundColor: colors.card,
    color: colors.text,
    borderRadius: radius.s,
    borderWidth: 1,
    borderColor: colors.border,
    padding: space.m - space.xs,
    fontSize: font.value,
  },
  hint: { color: colors.muted, fontSize: font.small },
  warn: { color: colors.warn, fontSize: font.body, marginTop: space.s },
  button: {
    backgroundColor: colors.accent,
    borderRadius: radius.s,
    padding: space.m,
    alignItems: 'center',
    marginTop: space.m,
  },
  secondary: { backgroundColor: colors.border, marginTop: space.s },
  dim: { opacity: 0.5 },
  buttonText: { color: colors.onAccent, fontWeight: '600', fontSize: font.value },
  card: { backgroundColor: colors.card, borderRadius: radius.s, padding: space.m, marginTop: space.s },
  notice: { fontSize: font.value },
});
