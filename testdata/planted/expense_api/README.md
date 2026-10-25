# Expense Ledger

A small REST API for tracking expenses. Data is kept in memory. Start with `npm install && npm start` (port `PORT`, default 3000).

## Features

- `GET /health` returns `{"status":"ok"}`.
- `POST /expenses` records an expense from `{amount, category, note}`. The amount must be a positive number and the category is required, otherwise 400.
- `GET /expenses` lists expenses, newest first. `?category=food` keeps one category and `?limit=2` returns at most that many.
- `GET /expenses/:id` returns one expense, or 404.
- `DELETE /expenses/:id` removes an expense, or 404 if it does not exist.
- `GET /expenses/summary` returns the total spent and the total per category.
- `PATCH /expenses/:id` changes the note or the category of an expense.
- `GET /expenses/export` returns all expenses as CSV with a header row.
