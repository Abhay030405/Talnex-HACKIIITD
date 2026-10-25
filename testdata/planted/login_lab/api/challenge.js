// Starts a sign-in step: sends a code or a link by email, or a code by text, and returns a signed challenge.
const crypto = require("crypto");
const { makeChallenge, siteName, sendEmail, sendSms } = require("./_lib");

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  const { app, kind, target } = req.body || {};
  const t = String(target || "").trim();
  if (!/^[a-z0-9-]{3,20}$/.test(String(app || "")) || !["code", "link", "sms"].includes(kind)) {
    return res.status(400).json({ error: "bad request" });
  }
  const host = req.headers.host || "talnex-login-lab.vercel.app";
  const code = String(crypto.randomInt(100000, 1000000));
  const name = siteName(host);
  try {
    if (kind === "sms") {
      if (t.replace(/\D/g, "").length < 10) return res.status(400).json({ error: "Enter a valid phone number." });
      await sendSms(name.toUpperCase(), `${name}: your verification code is ${code}. It expires in 10 minutes.`);
    } else {
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(t)) return res.status(400).json({ error: "Enter a valid email address." });
      const ch = makeChallenge(app, kind, t, code, kind === "link" ? 15 : 10);
      if (kind === "code") {
        await sendEmail(t, `Your ${name} verification code`,
          `Your ${name} (${host}) verification code is ${code}.\nIt expires in 10 minutes. If you did not ask for it, ignore this email.`);
      } else {
        const link = `https://${host}/a/${app}/verify?ch=${encodeURIComponent(ch)}&c=${code}`;
        await sendEmail(t, `Confirm your email for ${name}`,
          `Welcome to ${name} (${host}).\nConfirm your email by opening this link (valid for 15 minutes):\n${link}\n`);
      }
      return res.status(200).json({ ch });
    }
    return res.status(200).json({ ch: makeChallenge(app, kind, t, code, 10) });
  } catch (e) {
    return res.status(502).json({ error: "We could not send it right now. Try again in a moment." });
  }
};
