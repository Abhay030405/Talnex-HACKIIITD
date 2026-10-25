// Shared helpers for the login lab: signed challenges (no database) and the two senders.
const crypto = require("crypto");

const need = (name) => {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not set`);
  return v;
};

const b64 = (s) => Buffer.from(s).toString("base64url");
const mac = (payload, code) =>
  crypto.createHmac("sha256", need("LAB_SECRET")).update(`${payload}:${code}`).digest("base64url");

function makeChallenge(app, kind, target, code, minutes) {
  const payload = b64(JSON.stringify({ a: app, k: kind, t: target, e: Date.now() + minutes * 60000 }));
  return `${payload}.${mac(payload, code)}`;
}

function checkChallenge(ch, code) {
  const [payload, sig] = String(ch || "").split(".");
  if (!payload || !sig) return null;
  const want = Buffer.from(mac(payload, String(code || "").trim()));
  const got = Buffer.from(sig);
  if (want.length !== got.length || !crypto.timingSafeEqual(want, got)) return null;
  const data = JSON.parse(Buffer.from(payload, "base64url").toString());
  return data.e > Date.now() ? data : { expired: true };
}

const siteName = (host) => String(host || "talnex-login-lab").split(".")[0];

async function sendEmail(to, subject, text) {
  const inbox = encodeURIComponent(need("AGENTMAIL_INBOX"));
  const base = process.env.AGENTMAIL_BASE_URL || "https://api.agentmail.to";
  const r = await fetch(`${base}/v0/inboxes/${inbox}/messages/send`, {
    method: "POST",
    headers: { Authorization: `Bearer ${need("AGENTMAIL_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ to, subject, text }),
  });
  if (!r.ok) throw new Error(`mail ${r.status}`);
}

// The lab has no SMS provider, so the text "arrives" the way a real one does on the team phone:
// it is posted to the TalNex phone endpoint with the gateway key, exactly as the SMS relay app does.
async function sendSms(from, body) {
  const base = need("SMS_PUBLIC_URL").replace(/\/$/, "");
  const r = await fetch(`${base}/v1/sms/incoming`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Gateway-Key": need("SMS_GATEWAY_KEY") },
    body: JSON.stringify({ from, body, received_at: new Date().toISOString(), device: "login-lab" }),
  });
  if (!r.ok) throw new Error(`sms ${r.status}`);
}

module.exports = { makeChallenge, checkChallenge, siteName, sendEmail, sendSms };
