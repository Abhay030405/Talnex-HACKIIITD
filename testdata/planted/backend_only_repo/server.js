const express = require("express");
const app = express();
app.use(express.json());

let items = [];
let nextId = 1;

const validUrl = (u) => typeof u === "string" && /^https?:\/\/\S+\.\S+/.test(u);
const validTitle = (t) => typeof t === "string" && t.trim().length > 0;

app.get("/health", (req, res) => res.json({ status: "ok" }));

app.post("/bookmarks", (req, res) => {
  const { url, title, tags } = req.body || {};
  if (!validUrl(url)) return res.status(400).json({ error: "url must be a valid http(s) address" });
  if (!validTitle(title)) return res.status(400).json({ error: "title is required" });
  const b = { id: nextId++, url, title: title.trim(), tags: Array.isArray(tags) ? tags : [], created: Date.now() };
  items.push(b);
  res.status(201).json(b);
});

app.get("/bookmarks", (req, res) => {
  let out = [...items].sort((a, b) => b.created - a.created || b.id - a.id);
  if (req.query.tag) out = out.filter((b) => b.tags.includes(req.query.tag));
  res.json(out);
});

app.get("/bookmarks/:id", (req, res) => {
  const b = items.find((x) => x.id === Number(req.params.id));
  if (!b) return res.status(404).json({ error: "not found" });
  res.json(b);
});

// BUG (planted): no validation here, so an empty url or title is accepted.
app.put("/bookmarks/:id", (req, res) => {
  const b = items.find((x) => x.id === Number(req.params.id));
  if (!b) return res.status(404).json({ error: "not found" });
  Object.assign(b, req.body);
  res.json(b);
});

app.delete("/bookmarks/:id", (req, res) => {
  const i = items.findIndex((x) => x.id === Number(req.params.id));
  if (i < 0) return res.status(404).json({ error: "not found" });
  items.splice(i, 1);
  res.status(204).end();
});

// BUG (planted): an empty body (or one without a list) throws and the server answers 500.
app.post("/bookmarks/import", (req, res) => {
  let added = 0;
  for (const x of req.body.bookmarks) {
    if (validUrl(x.url) && validTitle(x.title)) {
      items.push({ id: nextId++, url: x.url, title: x.title.trim(), tags: x.tags || [], created: Date.now() });
      added++;
    }
  }
  res.status(201).json({ added });
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`Bookmark Keeper listening on ${port}`));
