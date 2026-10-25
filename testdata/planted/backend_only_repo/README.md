# Bookmark Keeper

A small REST API for saving bookmarks. Data is kept in memory. Start with `npm install && npm start` (port `PORT`, default 3000).

## Features

- `GET /health` returns `{"status":"ok"}`.
- `POST /bookmarks` saves a bookmark from `{url, title, tags}`. A missing or invalid `url` or an empty `title` is refused with 400.
- `GET /bookmarks` lists all bookmarks, newest first.
- `GET /bookmarks?tag=x` lists only bookmarks that have the tag.
- `GET /bookmarks/:id` returns one bookmark, or 404 if it does not exist.
- `PUT /bookmarks/:id` updates a bookmark. The same checks as when creating apply: a missing or invalid `url` or an empty `title` is refused with 400.
- `DELETE /bookmarks/:id` removes a bookmark (404 if it does not exist).
- `POST /bookmarks/import` takes `{bookmarks: [...]}` and adds each valid one. An empty or malformed body is refused with 400.
