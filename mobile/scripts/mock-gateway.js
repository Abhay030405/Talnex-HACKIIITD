// A stand-in for the server's POST /v1/sms/incoming, for trying the app before the real backend is running.
// It follows the same rules as the Go handler: key header, field limits, time checks, 60 messages a minute.
//
//   npm run mock-gateway
//   MOCK_GATEWAY_KEY=... MOCK_GATEWAY_PORT=8090 npm run mock-gateway

const http = require('node:http');
const os = require('node:os');

const PATH = '/v1/sms/incoming';
const BODY_LIMIT_BYTES = 8 * 1024;
const TEXT_MAX = 1000;
const FIELD_MAX = 100;
const MIN_KEY_LENGTH = 16;
const FUTURE_SLACK_MS = 5 * 60 * 1000;
const MAX_PER_MINUTE = 60;
const ISO_8601 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

const chars = (s) => Array.from(s).length;

/** Checks one request the way the server does. Returns the status code and, on failure, the error words. */
function checkIncoming({ key, gotKey, rawBody, now = Date.now() }) {
  if (!key || key.length < MIN_KEY_LENGTH) return { status: 503, error: 'phone sign-up is switched off' };
  if (gotKey !== key) return { status: 401, error: 'wrong gateway key' };
  if (Buffer.byteLength(rawBody) > BODY_LIMIT_BYTES) return { status: 400, error: 'the message could not be read' };
  let msg;
  try {
    msg = JSON.parse(rawBody);
  } catch {
    return { status: 400, error: 'the message could not be read' };
  }
  if (!msg || typeof msg !== 'object') return { status: 400, error: 'the message could not be read' };
  const { from = '', body = '', received_at: receivedAt = '', device = '' } = msg;
  if (![from, body, receivedAt, device].every((v) => typeof v === 'string')) {
    return { status: 400, error: 'the message could not be read' };
  }
  if (!from || !body) return { status: 400, error: 'from and body are required' };
  if (chars(body) > TEXT_MAX || chars(from) > FIELD_MAX || chars(device) > FIELD_MAX) {
    return { status: 400, error: 'a field is too long' };
  }
  const at = Date.parse(receivedAt);
  if (!ISO_8601.test(receivedAt) || Number.isNaN(at)) {
    return { status: 400, error: 'received_at must be an ISO 8601 time' };
  }
  if (at > now + FUTURE_SLACK_MS) return { status: 400, error: 'received_at is in the future' };
  return { status: 202, message: { from, body, received_at: receivedAt, device } };
}

/** Starts nothing by itself: call .listen() on the returned server. `received` collects accepted messages. */
function createMockGateway({ key, log = () => {} }) {
  const received = [];
  let times = [];

  const server = http.createServer((req, res) => {
    const reply = (status, error) => {
      res.writeHead(status, { 'Content-Type': 'application/json' });
      res.end(error ? JSON.stringify({ error }) : '');
    };
    if (req.method !== 'POST' || req.url !== PATH) return reply(404, 'not found');

    const parts = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size <= BODY_LIMIT_BYTES + 1) parts.push(chunk);
    });
    req.on('end', () => {
      const now = Date.now();
      times = times.filter((t) => t > now - 60_000);
      if (key && key.length >= MIN_KEY_LENGTH && req.headers['x-gateway-key'] === key) {
        if (times.length >= MAX_PER_MINUTE) return reply(429, 'too many messages, slow down');
        times.push(now);
      }
      const result = checkIncoming({
        key,
        gotKey: req.headers['x-gateway-key'],
        rawBody: Buffer.concat(parts).toString('utf8'),
        now,
      });
      if (result.message) {
        received.push(result.message);
        log(`accepted  from=${result.message.from}  device=${result.message.device}  body=${result.message.body}`);
      } else {
        log(`refused   ${result.status} ${result.error}`);
      }
      reply(result.status, result.error);
    });
  });

  return { server, received };
}

function lanAddresses() {
  return Object.values(os.networkInterfaces())
    .flat()
    .filter((a) => a && a.family === 'IPv4' && !a.internal)
    .map((a) => a.address);
}

if (require.main === module) {
  const key = process.env.MOCK_GATEWAY_KEY || 'mock-gateway-key-change-me';
  const port = Number(process.env.MOCK_GATEWAY_PORT || 8090);
  const { server } = createMockGateway({ key, log: (line) => console.log(`${new Date().toISOString()}  ${line}`) });
  server.listen(port, '0.0.0.0', () => {
    console.log(`Mock SMS gateway listening on port ${port}. Type one of these into the app:`);
    for (const ip of lanAddresses()) console.log(`  http://${ip}:${port}${PATH}`);
    console.log(`Key: ${key}`);
  });
}

module.exports = { PATH, checkIncoming, createMockGateway };
