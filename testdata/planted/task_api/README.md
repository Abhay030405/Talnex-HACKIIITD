# Task Board API

A small Flask API for to-do tasks. Data is kept in memory. Start with `pip install -r requirements.txt && python app.py` (port `PORT`, default 5000).

## Features

- `GET /health` returns `{"status":"ok"}`.
- `POST /tasks` creates a task from `{title, priority}`. The title is required and the priority must be a whole number from 1 to 5 (default 3), otherwise 400.
- `GET /tasks` lists tasks. `?done=true` or `?done=false` filters by state, and the list is sorted by priority, highest first.
- `GET /tasks/<id>` returns one task, or 404.
- `PATCH /tasks/<id>` renames a task. An empty title is refused with 400.
- `POST /tasks/<id>/complete` marks a task done, or 404 if it does not exist.
- `DELETE /tasks/<id>` deletes a task, or 404 if it does not exist.
- `GET /stats` returns how many tasks are `total`, `done` and `open`.
