// Checks a code (typed, or taken from an emailed link) against its signed challenge.
const { checkChallenge } = require("./_lib");

module.exports = (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  const { ch, code } = req.body || {};
  const data = checkChallenge(ch, code);
  if (!data) return res.status(400).json({ error: "That code is not right." });
  if (data.expired) return res.status(400).json({ error: "That code has expired. Ask for a new one." });
  return res.status(200).json({ ok: true, target: data.t, kind: data.k });
};
