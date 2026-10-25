const express = require("express");
const app = express();
app.use(express.json());

let expenses = [];
let nextId = 1;

app.get("/health", (req, res) => res.json({ status: "ok" }));

// BUG (planted): a negative or zero amount is accepted because only the type is checked.
app.post("/expenses", (req, res) => {
  const { amount, category, note } = req.body || {};
  if (typeof amount !== "number" || Number.isNaN(amount)) return res.status(400).json({ error: "amount must be a number" });
  if (!category || typeof category !== "string") return res.status(400).json({ error: "category is required" });
  const e = { id: nextId++, amount, category, note: note || "", created: Date.now() };
  expenses.push(e);
  res.status(201).json(e);
});

app.get("/expenses", (req, res) => {
  let out = [...expenses].sort((a, b) => b.id - a.id);
  if (req.query.category) out = out.filter((e) => e.category === req.query.category);
  if (req.query.limit) out = out.slice(0, Math.max(0, parseInt(req.query.limit, 10) || 0));
  res.json(out);
});

// BUG (planted): the per-category totals only count the first expense of each category.
app.get("/expenses/summary", (req, res) => {
  const byCategory = {};
  for (const e of expenses) if (!(e.category in byCategory)) byCategory[e.category] = e.amount;
  const total = expenses.reduce((n, e) => n + e.amount, 0);
  res.json({ total, byCategory });
});

app.get("/expenses/export", (req, res) => {
  const rows = expenses.map((e) => [e.id, e.amount, JSON.stringify(e.category), JSON.stringify(e.note)].join(","));
  res.type("text/csv").send(["id,amount,category,note", ...rows].join("\n") + "\n");
});

app.get("/expenses/:id", (req, res) => {
  const e = expenses.find((x) => x.id === Number(req.params.id));
  if (!e) return res.status(404).json({ error: "not found" });
  res.json(e);
});

app.patch("/expenses/:id", (req, res) => {
  const e = expenses.find((x) => x.id === Number(req.params.id));
  if (!e) return res.status(404).json({ error: "not found" });
  if (typeof req.body.note === "string") e.note = req.body.note;
  if (typeof req.body.category === "string" && req.body.category) e.category = req.body.category;
  res.json(e);
});

app.delete("/expenses/:id", (req, res) => {
  const i = expenses.findIndex((x) => x.id === Number(req.params.id));
  if (i < 0) return res.status(404).json({ error: "not found" });
  expenses.splice(i, 1);
  res.status(204).end();
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`Expense Ledger listening on ${port}`));
