"""Find the HTTP routes a backend defines, without running it (architecture 28.6, sources 1 to 3). Pure functions.

Three sources, each with its own limits, merged later by a model that also maps routes to claims:
  1. an OpenAPI / Swagger document (the most reliable when it exists),
  2. route definitions read from the code (Express, Fastify, Koa-style routers, Flask, FastAPI, Django, Spring, Gin),
  3. endpoints written in the README.

Code reading is by pattern, not by running or fully understanding the program, so a route it finds is a candidate, not
a fact: the test stage proves each one by calling it, and a route that does not exist is simply "not found", never a mark
against the project. Mounted routers and blueprints get their prefix when it is written next to where they are mounted.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Optional

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")
CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".go", ".java", ".kt", ".rb", ".php"}
# A call like axios.get('/api/x') or supertest(app).get('/x') is a request being made, not a route being defined.
NOT_ROUTERS = {"axios", "http", "https", "api", "request", "supertest", "fetch", "client", "agent", "$http", "got", "superagent",
               "self", "cy", "session", "requests", "httpx", "ky", "needle", "this"}


@dataclass(frozen=True)
class FoundRoute:
    method: str                       # GET, POST, ... or ANY when the code does not say
    path: str                         # always starts with /
    source: str                       # openapi / code / readme
    file: str = ""
    line: int = 0
    summary: str = ""
    body_fields: tuple[str, ...] = ()
    needs_auth: Optional[bool] = None  # None = unknown

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, normalise_path(self.path))


def normalise_path(path: str) -> str:
    """One spelling for a route path: leading slash, no trailing slash, {id} / :id / <id> all written as {}."""
    path = "/" + path.strip().lstrip("/")
    path = re.sub(r"\{[^}/]*\}|:[A-Za-z_]\w*|<[^>/]*>|\[[^\]/]*\]", "{}", path)
    return path.rstrip("/") or "/"


def join_paths(prefix: str, path: str) -> str:
    return "/" + "/".join(p for p in (prefix.strip("/"), path.strip("/")) if p)


# ---------------------------------------------------------------- 1. OpenAPI


def from_openapi(text_or_doc) -> list[FoundRoute]:
    """Routes from an OpenAPI 3 or Swagger 2 document given as JSON text or an already parsed dict."""
    doc = text_or_doc
    if isinstance(doc, (str, bytes)):
        try:
            doc = json.loads(doc)
        except ValueError:
            return []
    if not isinstance(doc, dict) or not isinstance(doc.get("paths"), dict):
        return []
    secured_everywhere = bool(doc.get("security"))
    out: list[FoundRoute] = []
    base = ""
    if isinstance(doc.get("basePath"), str):  # Swagger 2
        base = doc["basePath"]
    for path, item in doc["paths"].items():
        if not isinstance(item, dict) or not isinstance(path, str):
            continue
        for method, op in item.items():
            if method.upper() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            fields = _openapi_body_fields(op, doc)
            out.append(FoundRoute(
                method.upper(), join_paths(base, path), "openapi", summary=str(op.get("summary") or op.get("description") or "")[:200],
                body_fields=tuple(fields), needs_auth=bool(op.get("security") or secured_everywhere) if ("security" in op or secured_everywhere) else None))
    return out


def _resolve(ref: str, doc: dict):
    node = doc
    for part in ref.lstrip("#/").split("/"):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _openapi_body_fields(op: dict, doc: dict) -> list[str]:
    schema = None
    body = op.get("requestBody")
    if isinstance(body, dict):
        for media in (body.get("content") or {}).values():
            schema = (media or {}).get("schema")
            break
    for param in op.get("parameters") or []:  # Swagger 2 puts the body in a parameter
        if isinstance(param, dict) and param.get("in") == "body":
            schema = param.get("schema")
    for _ in range(3):
        if isinstance(schema, dict) and "$ref" in schema:
            schema = _resolve(schema["$ref"], doc)
    if isinstance(schema, dict) and isinstance(schema.get("properties"), dict):
        return sorted(schema["properties"])
    return []


# ---------------------------------------------------------------- 2. the code


_JS_ROUTE = re.compile(r"""(?P<recv>[$\w.]+)\.(?P<m>get|post|put|patch|delete|options|head|all)\(\s*(?P<q>['"`])(?P<p>/[^'"`]*)(?P=q)""")
_JS_MOUNT = re.compile(r"""\.use\(\s*(?P<q>['"`])(?P<p>/[^'"`]*)(?P=q)\s*,\s*(?P<arg>[^\n]+)""")
_JS_IMPORT = re.compile(r"""(?:const|let|var)\s+(?P<n>\w+)\s*=\s*require\(\s*['"](?P<f>[^'"]+)['"]\s*\)|import\s+(?P<n2>\w+)\s+from\s+['"](?P<f2>[^'"]+)['"]""")
_PY_DECORATOR = re.compile(r"""^\s*@(?P<recv>\w+)\.(?P<m>get|post|put|patch|delete|route)\(\s*(?P<q>['"])(?P<p>[^'"]*)(?P=q)(?P<rest>[^)]*)\)""", re.M)
_PY_METHODS = re.compile(r"methods\s*=\s*[\[(]([^\])]*)[\])]")
_PY_BLUEPRINT = re.compile(r"""(?P<n>\w+)\s*=\s*(?:flask\.)?Blueprint\([^)]*?url_prefix\s*=\s*['"](?P<p>[^'"]*)['"]""")
_PY_ROUTER = re.compile(r"""(?P<n>\w+)\s*=\s*(?:fastapi\.)?APIRouter\([^)]*?prefix\s*=\s*['"](?P<p>[^'"]*)['"]""")
_PY_REGISTER = re.compile(r"""\.(?:register_blueprint|include_router)\(\s*(?P<n>[\w.]+)[^)]*?(?:url_prefix|prefix)\s*=\s*['"](?P<p>[^'"]*)['"]""")
_DJANGO = re.compile(r"""\bpath\(\s*['"](?P<p>[^'"]*)['"]""")
_SPRING = re.compile(r"""@(?P<m>Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*)?['"](?P<p>[^'"]*)['"]""")
_GIN = re.compile(r"""\.(?P<m>GET|POST|PUT|DELETE|PATCH)\(\s*"(?P<p>/[^"]*)\"""")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


_JS_BODY = re.compile(r"""req\.body\.(\w+)|req\.body\[['"](\w+)['"]\]|\{([^{}]{1,200})\}\s*=\s*req\.body""")
_PY_BODY = re.compile(r"""(?:request\.(?:json|form|args)|\bdata|\bbody|\bpayload|\bjson_data)\s*(?:\[\s*['"](\w+)['"]\s*\]|\.get\(\s*['"](\w+)['"])""")
_NOT_FIELDS = {"length", "toString", "constructor", "keys", "values", "items", "get", "json"}


def body_fields_near(text: str, start: int, suffix: str, lines: int = 40) -> tuple[str, ...]:
    """The request fields a handler reads, looked for in the lines right after its route line (until the next route)."""
    window = "\n".join(text[start:].splitlines()[:lines])
    pattern = _JS_ROUTE if suffix != ".py" else _PY_DECORATOR
    current = pattern.match(window)
    nxt = pattern.search(window, current.end() if current else 1)
    if nxt:
        window = window[: nxt.start()]
    found: list[str] = []
    if suffix == ".py":
        for m in _PY_BODY.finditer(window):
            found.append(m.group(1) or m.group(2))
    else:
        for m in _JS_BODY.finditer(window):
            if m.group(3):
                found += [p.split(":")[0].split("=")[0].strip() for p in m.group(3).split(",")]
            else:
                found.append(m.group(1) or m.group(2))
    out: list[str] = []
    for f in found:
        if f and re.fullmatch(r"\w+", f) and f not in _NOT_FIELDS and f not in out:
            out.append(f)
    return tuple(out[:8])


def from_code(files: Mapping[str, str]) -> list[FoundRoute]:
    """Routes defined in source files. `files` maps repo-relative path to its text."""
    prefixes = _mounted_prefixes(files)
    out: list[FoundRoute] = []
    for path, text in sorted(files.items()):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix not in CODE_SUFFIXES:
            continue
        file_prefix = prefixes.get(path, "")
        if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            for m in _JS_ROUTE.finditer(text):
                if m["recv"].split(".")[0].lower() in NOT_ROUTERS or m["recv"].lower() in NOT_ROUTERS:
                    continue
                method = "ANY" if m["m"] == "all" else m["m"].upper()
                out.append(FoundRoute(method, join_paths(file_prefix, m["p"]), "code", path, _line_of(text, m.start()),
                                      body_fields=body_fields_near(text, m.start(), suffix) if method in ("POST", "PUT", "PATCH") else ()))
        elif suffix == ".py":
            out += _python_routes(path, text, file_prefix)
        elif suffix in {".java", ".kt"}:
            for m in _SPRING.finditer(text):
                out.append(FoundRoute(m["m"].upper(), join_paths("", m["p"]), "code", path, _line_of(text, m.start())))
        elif suffix == ".go":
            for m in _GIN.finditer(text):
                out.append(FoundRoute(m["m"], join_paths("", m["p"]), "code", path, _line_of(text, m.start())))
    return _unique(out)


def _python_routes(path: str, text: str, file_prefix: str) -> list[FoundRoute]:
    out: list[FoundRoute] = []
    local = {m["n"]: m["p"] for m in _PY_BLUEPRINT.finditer(text)} | {m["n"]: m["p"] for m in _PY_ROUTER.finditer(text)}
    for m in _PY_DECORATOR.finditer(text):
        verb = m["m"]
        if verb == "route":
            found = _PY_METHODS.search(m["rest"])
            methods = [x.strip(" '\"").upper() for x in found.group(1).split(",") if x.strip(" '\"")] if found else ["GET"]
        else:
            methods = [verb.upper()]
        prefix = join_paths(file_prefix, local.get(m["recv"], "")) if (file_prefix or local.get(m["recv"])) else ""
        for method in methods:
            out.append(FoundRoute(method, join_paths(prefix, m["p"]), "code", path, _line_of(text, m.start()),
                                  body_fields=body_fields_near(text, m.start(), ".py") if method in ("POST", "PUT", "PATCH") else ()))
    if PurePosixPath(path).name == "urls.py":
        for m in _DJANGO.finditer(text):
            out.append(FoundRoute("ANY", join_paths(file_prefix, m["p"]), "code", path, _line_of(text, m.start())))
    return out


def _mounted_prefixes(files: Mapping[str, str]) -> dict[str, str]:
    """{file: prefix} for router files mounted with a prefix: app.use('/api', usersRouter), register_blueprint(bp, url_prefix=...)."""
    by_stem: dict[str, list[str]] = {}
    for f in files:
        by_stem.setdefault(PurePosixPath(f).stem.lower(), []).append(f)
    result: dict[str, str] = {}
    for path, text in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            imports = {}
            for m in _JS_IMPORT.finditer(text):
                imports[m["n"] or m["n2"]] = m["f"] or m["f2"]
            for m in _JS_MOUNT.finditer(text):
                arg = m["arg"].strip()
                name = re.match(r"\w+", arg)
                inline = re.search(r"""require\(\s*['"]([^'"]+)['"]\s*\)""", arg)
                target = imports.get(name.group(0)) if name else None
                target = target or (inline.group(1) if inline else None)
                if target:
                    for f in by_stem.get(PurePosixPath(target).stem.lower(), []):
                        if f != path:
                            result[f] = join_paths(result.get(path, ""), m["p"])
        elif suffix == ".py":
            for m in _PY_REGISTER.finditer(text):
                name = m["n"].split(".")[-1]
                stem = name.removesuffix("_bp").removesuffix("_blueprint").removesuffix("_router").removesuffix("_api").lower()
                for key in (name.lower(), stem):
                    for f in by_stem.get(key, []):
                        if f != path:
                            result[f] = m["p"]
    return result


def _unique(routes: Iterable[FoundRoute]) -> list[FoundRoute]:
    seen: set[tuple[str, str, str, int]] = set()
    out: list[FoundRoute] = []
    for r in routes:
        k = (r.method, normalise_path(r.path), r.file, r.line)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


# ---------------------------------------------------------------- 3. the README


_README_LINE = re.compile(r"""(?:^|[\s`|*>-])(?P<m>GET|POST|PUT|PATCH|DELETE)[\s|`]+(?P<p>/[A-Za-z0-9_\-./:{}<>\[\]]*)`?""", re.M)


def from_readme(text: str) -> list[FoundRoute]:
    """Endpoints the README lists, like `GET /api/items` or a table row `| POST | /login |`."""
    out = []
    for m in _README_LINE.finditer(text or ""):
        out.append(FoundRoute(m["m"], join_paths("", m["p"]), "readme", "README.md", _line_of(text, m.start())))
    return _unique(out)


# ---------------------------------------------------------------- putting them together


def merge(*groups: Iterable[FoundRoute]) -> list[FoundRoute]:
    """One list with each (method, path) once. OpenAPI wins over code, code over README, and the facts that only
    one source knows (body fields, auth) are kept."""
    rank = {"openapi": 0, "code": 1, "readme": 2}
    best: dict[tuple[str, str], FoundRoute] = {}
    for route in sorted((r for g in groups for r in g), key=lambda r: (rank.get(r.source, 9), r.file, r.line)):
        current = best.get(route.key)
        if current is None:
            best[route.key] = route
            continue
        updates = {}
        if not current.body_fields and route.body_fields:
            updates["body_fields"] = route.body_fields
        if current.needs_auth is None and route.needs_auth is not None:
            updates["needs_auth"] = route.needs_auth
        if not current.summary and route.summary:
            updates["summary"] = route.summary
        if updates:
            best[route.key] = FoundRoute(**{**current.__dict__, **updates})
    # An "ANY" route is covered by a specific method on the same path, so keep it only when nothing else is known.
    specific = {path for (method, path) in best if method != "ANY"}
    kept = [r for k, r in best.items() if not (r.method == "ANY" and k[1] in specific)]
    return sorted(kept, key=lambda r: (normalise_path(r.path), r.method))
