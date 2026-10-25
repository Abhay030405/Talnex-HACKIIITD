import os

from flask import Flask, jsonify, request

app = Flask(__name__)
tasks = {}
next_id = 1


def not_found():
    return jsonify(error="not found"), 404


@app.get("/health")
def health():
    return jsonify(status="ok")


# BUG (planted): the priority is never checked, so 0, 99 or "high" are accepted.
@app.post("/tasks")
def create():
    global next_id
    body = request.get_json(silent=True) or {}
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        return jsonify(error="title is required"), 400
    task = {"id": next_id, "title": title.strip(), "priority": body.get("priority", 3), "done": False}
    tasks[next_id] = task
    next_id += 1
    return jsonify(task), 201


@app.get("/tasks")
def listing():
    out = list(tasks.values())
    done = request.args.get("done")
    if done in ("true", "false"):
        out = [t for t in out if t["done"] == (done == "true")]
    out.sort(key=lambda t: (-t["priority"] if isinstance(t["priority"], int) else 0, t["id"]))
    return jsonify(out)


@app.get("/tasks/<int:task_id>")
def one(task_id):
    task = tasks.get(task_id)
    return jsonify(task) if task else not_found()


@app.patch("/tasks/<int:task_id>")
def rename(task_id):
    task = tasks.get(task_id)
    if not task:
        return not_found()
    title = (request.get_json(silent=True) or {}).get("title")
    if not isinstance(title, str) or not title.strip():
        return jsonify(error="title is required"), 400
    task["title"] = title.strip()
    return jsonify(task)


@app.post("/tasks/<int:task_id>/complete")
def complete(task_id):
    task = tasks.get(task_id)
    if not task:
        return not_found()
    task["done"] = True
    return jsonify(task)


# BUG (planted): deleting an id that does not exist answers 204 as if it had worked.
@app.delete("/tasks/<int:task_id>")
def delete(task_id):
    tasks.pop(task_id, None)
    return "", 204


# BUG (planted): "open" counts every task, finished ones included.
@app.get("/stats")
def stats():
    done = sum(1 for t in tasks.values() if t["done"])
    return jsonify(total=len(tasks), done=done, open=len(tasks))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
