/**
 * @jest-environment node
 */
import { sendToGateway } from '../gateway';
import { buildPayload, buildTestPayload } from '../payload';
import type { Settings } from '../types';
import { nodeFetch } from './nodeFetch';

// Checks the app's sending code against a running TalNex server. Skipped unless both are set:
//   LIVE_GATEWAY_URL=http://localhost:8080 LIVE_GATEWAY_KEY=<SMS_GATEWAY_KEY> npm test -- liveGateway
// Every message it sends comes from "TalNex test" and is deleted by the server after 24 hours.
const url = process.env.LIVE_GATEWAY_URL ?? '';
const key = process.env.LIVE_GATEWAY_KEY ?? '';
const live = url && key ? describe : describe.skip;

live('the app against a running server', () => {
  const settings: Settings = { gatewayUrl: url, gatewayKey: key, deviceName: 'TalNex live check' };
  const send = (s: Settings, p = buildTestPayload(s.deviceName)) => sendToGateway(s, p, nodeFetch);

  it('delivers a message', async () => {
    expect(await send(settings)).toEqual({ outcome: 'ok', status: 202 });
  });

  it('delivers an over-long text after cutting it to the limits', async () => {
    const long = buildPayload(
      { from: 'TalNex test '.repeat(20), body: 'code 482913 '.repeat(200), receivedAt: new Date() },
      'TalNex live check '.repeat(10),
    );
    expect(await send(settings, long)).toEqual({ outcome: 'ok', status: 202 });
  });

  it('reports a wrong key', async () => {
    expect(await send({ ...settings, gatewayKey: `${key}-wrong` })).toEqual({ outcome: 'wrong_key', status: 401 });
  });

  it('reports a refused message', async () => {
    const future = buildTestPayload(settings.deviceName, new Date(Date.now() + 60 * 60 * 1000));
    expect(await send(settings, future)).toEqual({ outcome: 'rejected', status: 400 });
  });
});
