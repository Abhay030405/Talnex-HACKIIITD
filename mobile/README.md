# TalNex SMS Relay (`mobile/`)

An Android app for the team's spare phone with the team SIM. When a text arrives, for example a sign-up code from a site TalNex is testing, the app forwards it to the TalNex server so the login ladder can read it. It never sends texts and reads nothing but incoming SMS.

Expo SDK 57 (React Native 0.86, New Architecture), TypeScript.

## What it does

- **Status:** a big switch for SMS listening, the server address, how many texts were sent and how many are waiting, and the last 20 texts (sender, time, "sent" or "failed: reason"). The text itself is never kept in this list.
- **Settings:** server address, key and phone name. Typing just the server (`http://192.168.1.10:8080`) is enough: the app adds `/v1/sms/incoming`. The screen says what is wrong before you save (no `http://`, key too short), and **Send test message** answers in words: works, wrong key, switched off on the server, cannot reach it.
- **Waiting list:** a text that could not be delivered is kept and tried again when the app opens, when the connection returns, and every minute. It is removed as soon as it is sent. At most 200 wait. Texts older than a day are dropped (the server deletes texts after 24 hours anyway), and a text the server refuses as invalid is dropped instead of blocking the ones behind it.
- **Secrets:** the address and key are typed in the app and kept in the phone's secure storage (`expo-secure-store`). They are never in the code, never shown again and never logged.

## What it sends

`POST <address>` with headers `Content-Type: application/json` and `X-Gateway-Key: <key>`:

```json
{"from": "<sender>", "body": "<text>", "received_at": "<ISO 8601 UTC>", "device": "<phone name>"}
```

Long fields are cut to the server's limits (body 1000 characters, sender and phone name 100) so they are never refused for length.

| Server answer | The app |
|---|---|
| 200, 202 | sent |
| 401, 403 | wrong key, kept and retried |
| 400, 413 | refused as invalid, dropped |
| 429 | server busy, kept and retried |
| 503 | phone sign-up switched off on the server, kept and retried |
| other, or no answer | kept and retried |

## Try it without the backend: the mock server

`scripts/mock-gateway.js` stands in for the server's endpoint and follows the same rules (key, field limits, time checks, 60 texts a minute). It prints every text it accepts.

```
cd mobile
npm run mock-gateway
```

It prints the addresses to type into the phone and the key to use (set your own with `MOCK_GATEWAY_KEY`, and the port with `MOCK_GATEWAY_PORT`, default 8090). The phone and the PC must be on the same Wi-Fi. If Windows asks, allow Node through the firewall on private networks.

## Which address and key to type for the real server

- **Address:** `http://<your PC's LAN IP>:8080` (find the IP with `ipconfig`, "IPv4 Address"). Plain `http://` is allowed for local testing. Use `https://` for anything outside your own network.
- **Key:** the `SMS_GATEWAY_KEY` from the shared `.env`, at least 16 characters. Type it into the phone by hand. Never put it in this folder.
- **Phone name:** anything, for example `Team SIM phone`.

## Run in Expo Go (Settings and test message only)

```
cd mobile
npm install
npx expo start
```

Scan the QR code with Expo Go. Status shows "SMS listening needs the Android development build", because Expo Go has no SMS module. Settings and **Send test message** work, on iOS too.

## Android development build (real SMS)

You need Android Studio (for the Android SDK), JDK 17 or newer, and the phone with **USB debugging** on (Settings > About phone > tap Build number 7 times, then Developer options > USB debugging).

1. Plug the phone in and allow debugging on it.
2. `cd mobile && npm install`
3. `npx expo run:android`. The first build takes several minutes and creates `android/`, which is not committed.
4. The app opens on the phone. If asked, let it connect to Metro (same Wi-Fi), or run `npx expo start --dev-client` and open the app.

No Android Studio: use EAS (free account). `npm i -g eas-cli`, `eas login`, `eas build:configure`, then `eas build --profile development --platform android` with `"developmentClient": true` and `"distribution": "internal"` in that profile. Install the APK it gives you and run `npx expo start --dev-client`.

On the phone:

1. **Settings:** type the address, key and phone name, **Save**, then **Send test message**. It must say "Works".
2. **Status:** flip the switch on, and tap **Allow** when Android asks about SMS. Some phones block this for apps from outside the Play Store: open Settings > Apps > TalNex SMS Relay, use "Allow restricted settings" from the three-dot menu, then allow SMS under Permissions.
3. Text the team SIM from another phone. It shows in "Last 20 messages" as sent.

Keeping it running: the listener lives while the app does. Leave the app open (the screen can be off), keep the phone charging, and set the app's battery use to **Unrestricted**. If Android kills the app, open it again: listening turns itself back on.

## The SMS library and its limits

`@maniac-tech/react-native-expo-read-sms` 9.1.2 (MIT). It is the one maintained Expo-friendly library for incoming SMS, and it uses only the RECEIVE_SMS and READ_SMS permissions. The app calls its native module directly from `src/sms/listener.ts`, because its own JS helpers add a new event listener on every start.

- It is not marked as tested on the New Architecture, so it is excluded from that `expo-doctor` check in `package.json`. It runs through React Native's compatibility layer. It has **not been tried on a real phone in this repo yet**.
- When its native start fails inside, it calls back neither success nor failure. The app gives up after 5 seconds and says so instead of hanging.
- A long text sent in several parts may arrive with only the last part.
- It writes the sender and text to Android's debug log. Do not leave the phone plugged into a computer running `adb logcat` if that matters.
- iOS cannot read SMS at all.

If it fails on the phone, the fallback is a small local Expo module with a manifest receiver. Only `src/sms/listener.ts` changes.

## Folder map

| Path | What |
|---|---|
| `App.tsx`, `index.ts` | Wires the screens, listener and retry triggers |
| `src/types.ts` | Shared shapes |
| `src/payload.ts` | Builds the JSON body, reads the library's text |
| `src/gateway.ts` | Sends with a 10 s timeout, turns answers into outcomes and words, checks settings |
| `src/queue.ts`, `src/history.ts` | Waiting list and the last 20 list |
| `src/relay.ts` | Send, keep, retry, one change at a time |
| `src/storage.ts` | Secure storage for settings, AsyncStorage for the rest |
| `src/sms/listener.ts` | The only SMS code, and a do-nothing version for Expo Go and iOS |
| `src/ui/` | Status and Settings screens, theme, display formatting |
| `src/__tests__/` | Unit tests, and a contract test against the mock server over real HTTP |
| `scripts/mock-gateway.js` | Local stand-in for the server's SMS endpoint |

## Checks

```
cd mobile
npm test
npm run typecheck
npx expo-doctor
```
