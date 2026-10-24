"""Work out how to install and start a repo, from its files. Pure functions: the facts come in, a recipe comes out.

Order of trust (architecture 28.5): the repo's own Dockerfile, the README's run steps, then the package files, then a
model-drafted guess (which lives in `fix.py`, because it needs a model and a failed build to learn from).

Backend counts more than frontend, so a repo with client/ and server/ runs the server. A frontend-only repo has nothing
to test over HTTP and ends as "could not run: frontend only", which is said plainly and never counts against anyone.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Optional

from talnex_ai.sandbox.stack_detect.envvalues import env_placeholders
from talnex_ai.sandbox.stack_detect.recipe import IMAGES, Recipe

MANIFESTS = ("package.json", "requirements.txt", "pyproject.toml", "Pipfile", "manage.py")
ENTRY_NAMES = ("main.py", "app.py", "server.py", "api.py", "run.py", "wsgi.py", "asgi.py", "index.py")
BACKEND_DIR_NAMES = {"server", "backend", "api", "back", "service", "services", "app", "src"}
NODE_BACKEND = {"express", "fastify", "koa", "@hapi/hapi", "hapi", "@nestjs/core", "hono", "restify", "sails",
                "apollo-server", "@apollo/server", "graphql-yoga", "@trpc/server", "polka", "feathers", "@feathersjs/feathers"}
NODE_FRONTEND = {"react-scripts", "vite", "@vue/cli-service", "@angular/core", "svelte", "parcel", "gatsby", "@sveltejs/kit"}
PY_BACKEND = {"fastapi", "flask", "django", "aiohttp", "tornado", "sanic", "starlette", "bottle", "falcon", "quart"}
SERVICE_HINTS = {
    "postgres": ("postgres", "psycopg", "asyncpg", "pg-promise", '"pg"', "sequelize", "typeorm", "prisma"),
    "mysql": ("mysql", "mysql2", "pymysql", "mariadb"),
    "mongodb": ("mongodb", "mongoose", "pymongo", "motor"),
    "redis": ("redis", "ioredis", "bullmq", "celery"),
}
README_START = re.compile(r"^(npm (run )?(start|dev)|yarn (start|dev)|pnpm (run )?(start|dev)|node \S+|python3? \S+\.py|python3? -m \S+|"
                          r"uvicorn \S+|flask( --app \S+)? run.*|gunicorn \S+|python3? manage\.py runserver.*|go run .*)$")
README_INSTALL = re.compile(r"^(npm (ci|install|i)\b.*|yarn( install)?|pnpm (i|install)\b.*|pip3? install .*|python3? -m pip install .*|poetry install.*)$")


@dataclass
class RepoFacts:
    """What was read from the cloned repo: the file names and the text of the files that decide how it runs."""

    files: list[str]
    texts: dict[str, str] = field(default_factory=dict)   # path -> text, for manifests, entry files, Dockerfile, README, .env.example

    def text(self, path: str) -> str:
        return self.texts.get(path, "")


def _join(directory: str, name: str) -> str:
    return f"{directory}/{name}" if directory else name


def _name(directory: str) -> str:
    return PurePosixPath(directory).name.lower() if directory else ""


# ---------------------------------------------------------------- directories that could hold the app


def candidate_dirs(files: list[str]) -> list[str]:
    """The repo root and up to two folder levels that hold a manifest, shallowest first."""
    found: set[str] = set()
    for f in files:
        p = PurePosixPath(f)
        if p.name in MANIFESTS and len(p.parts) <= 3 and not {"node_modules", "vendor", "venv", ".venv", "tests", "test", "docs", "examples"} & set(p.parts[:-1]):
            found.add("" if len(p.parts) == 1 else str(p.parent))
    return sorted(found, key=lambda d: (d.count("/") if d else -1, d))


def _node_deps(pkg: dict) -> set[str]:
    return set((pkg.get("dependencies") or {})) | set((pkg.get("devDependencies") or {}))


def _load_json(text: str) -> dict:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _py_dep_text(facts: RepoFacts, directory: str) -> str:
    return "\n".join(facts.text(_join(directory, n)).lower() for n in ("requirements.txt", "pyproject.toml", "Pipfile"))


def score_dir(facts: RepoFacts, directory: str) -> tuple[int, str]:
    """How likely a folder is the backend, and which stack it is. A folder with a manifest always gets a stack, even
    with a negative score (a frontend), so the caller can tell "frontend only" from "no package file at all"."""
    options: list[tuple[int, str]] = []
    pkg = _load_json(facts.text(_join(directory, "package.json")))
    if pkg:
        deps = _node_deps(pkg)
        score = 1 if (pkg.get("scripts") or {}).get("start") else 0
        score += 5 if deps & NODE_BACKEND else 0
        score += 3 if "next" in deps else 0
        score -= 4 if (deps & NODE_FRONTEND and not deps & NODE_BACKEND and "next" not in deps) else 0
        score += 3 if _name(directory) in BACKEND_DIR_NAMES - {"app", "src"} else 0
        options.append((score, "node"))
    py = _py_dep_text(facts, directory)
    if py.strip() or facts.text(_join(directory, "manage.py")):
        score = 5 if any(re.search(rf"(^|[\s\"'=<>~\[]){name}", py) for name in PY_BACKEND) else 0
        score += 3 if _name(directory) in BACKEND_DIR_NAMES - {"app", "src"} else 0
        score += 1 if any(_join(directory, n) in facts.files for n in ENTRY_NAMES) else 0
        options.append((score, "python"))
    return max(options) if options else (0, "unknown")


# ---------------------------------------------------------------- Dockerfile and README hints


def dockerfile_hints(text: str) -> dict:
    """The start command and the port a Dockerfile declares. A Dockerfile is the repo author's own word on how it runs."""
    cmd, port = "", None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"(?i)^CMD\s+(\[.*\])\s*$", line)
        if m:
            try:
                cmd = " ".join(json.loads(m.group(1)))
            except ValueError:
                pass
        elif re.match(r"(?i)^CMD\s+\S", line):
            cmd = re.sub(r"(?i)^CMD\s+", "", line)
        m = re.match(r"(?i)^EXPOSE\s+(\d+)", line)
        if m and port is None:
            port = int(m.group(1))
    return {"cmd": cmd, "port": port}


def readme_commands(text: str) -> dict:
    """Run steps from the README's code blocks: {"install": [...], "start": [...]}."""
    out: dict[str, list[str]] = {"install": [], "start": []}
    for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S):
        for raw in block.splitlines():
            line = raw.strip().lstrip("$ ").strip()
            if README_START.match(line) and line not in out["start"]:
                out["start"].append(line)
            elif README_INSTALL.match(line) and line not in out["install"]:
                out["install"].append(line)
    return out


# The placeholder values for a repo's .env.example live in envvalues.py (env_placeholders is imported above).


def services_needed(facts: RepoFacts, directory: str) -> list[str]:
    """Databases and caches the app seems to need, from its dependencies, .env.example and compose file."""
    haystack = "\n".join([
        _py_dep_text(facts, directory), facts.text(_join(directory, "package.json")).lower(),
        facts.text(_join(directory, ".env.example")).lower(), facts.text("docker-compose.yml").lower(),
        facts.text("docker-compose.yaml").lower(), facts.text(".env.example").lower(),
    ])
    return [name for name, hints in SERVICE_HINTS.items() if any(h in haystack for h in hints)]


# ---------------------------------------------------------------- the recipes


def _node_recipe(facts: RepoFacts, directory: str) -> Recipe:
    pkg = _load_json(facts.text(_join(directory, "package.json")))
    scripts, deps = pkg.get("scripts") or {}, _node_deps(pkg)
    has = lambda n: _join(directory, n) in facts.files  # noqa: E731
    if has("pnpm-lock.yaml"):
        install = "corepack pnpm install"
    elif has("yarn.lock"):
        install = "corepack yarn install"
    elif has("package-lock.json"):
        install = "npm ci --no-audit --no-fund || npm install --no-audit --no-fund"
    else:
        install = "npm install --no-audit --no-fund"

    notes: list[str] = []
    start, build = "", ""
    if scripts.get("start"):
        start = "npm start"
    elif scripts.get("dev") and deps & NODE_BACKEND:
        start = "npm run dev"
    else:
        main = pkg.get("main") or next((n for n in ("server.js", "app.js", "index.js", "src/index.js", "src/server.js", "src/app.js")
                                         if has(n)), "")
        if main:
            start = f"node {main}"
    if "next" in deps and scripts.get("build"):
        build = "npm run build"
        notes.append("Next.js: built before it starts")
    test = ""
    if scripts.get("test") and "no test specified" not in scripts["test"]:
        test = "npm test"
    env = {"PORT": "3000", "NODE_ENV": "development", **env_placeholders(facts.text(_join(directory, ".env.example")))}
    return Recipe(stack="node", image=IMAGES["node"], app_dir=directory, install_cmd=install, build_cmd=build, start_cmd=start,
                  env=env, services=services_needed(facts, directory), test_cmd=test, source="package_files",
                  confidence="high" if scripts.get("start") else "medium", notes=notes)


def _python_app(facts: RepoFacts, directory: str, pattern: str) -> Optional[tuple[str, str, str]]:
    """(file, module path, variable) of the first entry file that creates the app object, e.g. app = FastAPI()."""
    candidates = [f for f in facts.files if f.endswith(".py") and (f.startswith(directory + "/") if directory else True)
                  and (PurePosixPath(f).name in ENTRY_NAMES) and len(PurePosixPath(f).relative_to(directory or ".").parts) <= 3]
    for f in sorted(candidates, key=lambda x: (x.count("/"), x)):
        m = re.search(rf"^(\w+)\s*(?::[^=\n]+)?=\s*{pattern}\(", facts.text(f), re.M)
        if m:
            rel = str(PurePosixPath(f).relative_to(directory or "."))
            return rel, rel[:-3].replace("/", "."), m.group(1)
    return None


def _python_recipe(facts: RepoFacts, directory: str) -> Recipe:
    has = lambda n: _join(directory, n) in facts.files  # noqa: E731
    deps = _py_dep_text(facts, directory)
    notes: list[str] = []
    if has("requirements.txt"):
        install = "pip install --no-cache-dir -r requirements.txt"
    elif has("pyproject.toml"):
        install = "pip install --no-cache-dir ."
    elif has("Pipfile"):
        install = "pip install pipenv && pipenv install --system --skip-lock"
    else:
        install = ""
    start, port, confidence = "", None, "medium"
    if facts.text(_join(directory, "manage.py")) or "django" in deps:
        if has("manage.py"):
            start, port, confidence = "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000", 8000, "high"
    if not start and "fastapi" in deps:
        app = _python_app(facts, directory, r"FastAPI")
        if app:
            start, port, confidence = f"uvicorn {app[1]}:{app[2]} --host 0.0.0.0 --port 8000", 8000, "high"
            if "uvicorn" not in deps:
                install = (install + " && " if install else "") + "pip install --no-cache-dir uvicorn"
                notes.append("uvicorn was not in the dependency list, so it is installed to start the app")
    if not start and "flask" in deps:
        app = _python_app(facts, directory, r"Flask")
        if app:
            runs_itself = re.search(r"\.run\(", facts.text(_join(directory, app[0])))
            start = f"python {app[0]}" if runs_itself else f"flask --app {app[1]}:{app[2]} run --host 0.0.0.0 --port 5000"
            port, confidence = (None if runs_itself else 5000), "high"
    test = "python -m pytest -x -q" if ("pytest" in deps or any(f.startswith(_join(directory, "tests")) for f in facts.files)) else ""
    env = {"PYTHONUNBUFFERED": "1", **env_placeholders(facts.text(_join(directory, ".env.example")))}
    return Recipe(stack="python", image=IMAGES["python"], app_dir=directory, install_cmd=install, start_cmd=start, port=port,
                  env=env, services=services_needed(facts, directory), test_cmd=test, source="package_files",
                  confidence=confidence if start else "low", notes=notes)


def _unsupported_stack(files: list[str]) -> Optional[str]:
    names = {PurePosixPath(f).name for f in files}
    for marker, stack in (("go.mod", "Go"), ("pom.xml", "Java"), ("build.gradle", "Java"), ("build.gradle.kts", "Java"),
                          ("Cargo.toml", "Rust"), ("Gemfile", "Ruby"), ("composer.json", "PHP"), ("pubspec.yaml", "Dart")):
        if marker in names:
            return stack
    return None


def detect_recipe(facts: RepoFacts) -> Recipe:
    """The best recipe the files allow. A stack we cannot run yet comes back as `unknown` with the reason in `notes`."""
    scored = [(score_dir(facts, d), d) for d in candidate_dirs(facts.files)]
    scored = [(s, d) for s, d in scored if s[1] != "unknown"]
    if not scored:
        other = _unsupported_stack(facts.files)
        reason = (f"this looks like a {other} project and the sandbox has no {other} image yet" if other
                  else "no package file (package.json, requirements.txt, pyproject.toml) was found")
        return Recipe(stack="unknown", confidence="low", notes=[reason])
    (score, stack), directory = max(scored, key=lambda x: (x[0][0], -x[1].count("/")))
    recipe = _node_recipe(facts, directory) if stack == "node" else _python_recipe(facts, directory)

    docker = dockerfile_hints(facts.text(_join(directory, "Dockerfile")) or facts.text("Dockerfile"))
    if not recipe.start_cmd and docker["cmd"]:
        recipe = recipe.model_copy(update={"start_cmd": docker["cmd"], "source": "dockerfile", "confidence": "medium"})
    if recipe.port is None and docker["port"]:
        recipe = recipe.model_copy(update={"port": docker["port"]})
    readme = readme_commands(facts.text("README.md") or facts.text("readme.md") or facts.text("README"))
    if not recipe.start_cmd and readme["start"]:
        recipe = recipe.model_copy(update={"start_cmd": readme["start"][0], "source": "readme", "confidence": "low"})
        if not recipe.install_cmd and readme["install"]:
            recipe = recipe.model_copy(update={"install_cmd": readme["install"][0]})

    if score <= 0 and not recipe.start_cmd:
        return Recipe(stack="unknown", confidence="low",
                      notes=["this looks like a frontend only: no server was found, so there are no backend routes to test"])
    if not recipe.start_cmd:
        recipe = recipe.with_note("no way to start the app was found in the files")
    return recipe
