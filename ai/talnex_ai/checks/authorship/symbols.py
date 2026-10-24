"""Code structure for the code locator (authorship proof, A1, source 2). Pure functions.

tree-sitter is not a dependency, so this reads code by pattern, the same way route discovery does: functions, classes, components and
routes, each with the lines it spans (by indentation for Python, by braces for the brace languages). It is a way to point at likely
lines, not a full parser: a symbol it misses simply leaves the claim to the model, and a wrong range is caught by the confidence floor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_SYMBOL_LINES = 400           # a "symbol" longer than this is cut here, so one range never swallows a whole big file
ARROW_BODY_LINES = 60            # a symbol without braces (an arrow function returning an expression) spans at most this many lines
WHOLE_FILE_LINES = 150           # a file this short also counts as one symbol (a small component or route file)

_PY_DEF = re.compile(r"^(\s*)(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
_PY_ROUTE = re.compile(r"""^\s*@\s*[\w.]+\.(?:route|get|post|put|patch|delete|api_view)\s*\(\s*['"]([^'"]*)['"]""")
_BRACE_DEFS = (
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)"),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:public\s+)?(?:class|interface|struct|enum|trait|impl)\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:(?:public|private|protected|static|async|override|final|suspend|fun|def)\s+)+[\w<>\[\],? ]*?\b([A-Za-z_$][\w$]*)\s*\([^;]*$"),
    re.compile(r"^\s{2,}(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*[\w<>\[\]|, .]+)?\s*\{\s*$"),
)
_JS_ROUTE = re.compile(r"""^\s*[\w$.]+\.(get|post|put|patch|delete|all|use)\s*\(\s*['"`]([^'"`]+)['"`]""")
_NOT_NAMES = {"if", "for", "while", "switch", "catch", "return", "function", "else", "do", "try", "with", "new", "typeof", "await"}
_WHOLE_FILE_SUFFIXES = {".vue", ".svelte", ".html", ".htm", ".ejs", ".hbs", ".pug", ".jinja", ".jinja2", ".njk"}
_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

# Words that say nothing about which feature a piece of code belongs to.
GENERIC = frozenset("""
the and for with from into that this then than are was were has have can could will would should able allow allows using use uses used via
user users their your our its his her them they you all any each new get set handle handler index main app src lib utils util helper helpers
component components page pages api route routes router controller controllers model models view views service services module default
export function class const let var def init file files data value values item items props state test tests spec type types config
""".split())
SYNONYMS = {
    "login": {"signin", "auth", "session"}, "signin": {"login", "auth", "session"}, "logout": {"signout"},
    "signup": {"register", "registration"}, "register": {"signup"}, "pay": {"payment", "checkout", "stripe"},
    "payment": {"pay", "checkout", "stripe"}, "checkout": {"payment", "cart"}, "chat": {"message", "conversation"},
    "upload": {"image", "attachment"},"search": {"query", "filter"}, "comment": {"reply"}, "profile": {"account"},
}


def stem(word: str) -> str:
    """A rough word root, so "payments", "uploading" and "uploaded" meet "payment" and "upload"."""
    w = word.lower()
    for end in ("ing", "ed", "es", "s"):
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[: -len(end)]
    return w


def words_of(text: str) -> set[str]:
    """Word roots in a name or a sentence: camelCase, snake_case, kebab-case and plain words are all split."""
    out: set[str] = set()
    for chunk in re.split(r"[^A-Za-z0-9]+", text):
        for part in _SPLIT.findall(chunk):
            if len(part) >= 3 and part.lower() not in GENERIC:
                out.add(stem(part))
    joined = re.sub(r"[^a-z]", "", text.lower())
    for compound in ("signin", "signup", "signout", "login", "logout", "checkout"):
        if compound in joined:
            out.add(compound)
    return out


def claim_words(text: str) -> set[str]:
    """The claim's word roots plus a few common synonyms, so "Sign in" also meets `login` and `auth`."""
    base = words_of(text)
    extra = {s for w in base for s in SYNONYMS.get(w, ())}
    return base | {stem(w) for w in extra}


@dataclass(frozen=True)
class Symbol:
    path: str
    name: str
    kind: str          # function / class / route / file
    start: int         # 1-based, inclusive
    end: int

    @property
    def words(self) -> set[str]:
        return words_of(self.name)


def _python_symbols(path: str, lines: list[str]) -> list[Symbol]:
    out: list[Symbol] = []
    for i, line in enumerate(lines):
        m = _PY_DEF.match(line)
        if not m:
            continue
        indent = len(m.group(1).expandtabs())
        start = i
        names = [m.group(3)]
        while start > 0 and lines[start - 1].strip().startswith("@"):
            start -= 1
            route = _PY_ROUTE.match(lines[start])
            if route:
                names.append(route.group(1))
        end = i
        for j in range(i + 1, len(lines)):
            text = lines[j]
            if text.strip() and len(text) - len(text.lstrip()) <= indent and not text.strip().startswith((")", "]", "}")):
                break
            if text.strip():
                end = j
        end = min(end, start + MAX_SYMBOL_LINES - 1)
        out.append(Symbol(path, " ".join(names), "class" if m.group(2) == "class" else "function", start + 1, end + 1))
    return out


def _brace_end(lines: list[str], i: int) -> int:
    """The line where the block opened on (or just after) line i closes. Strings and comments are only roughly skipped."""
    depth, opened = 0, False
    for j in range(i, min(len(lines), i + MAX_SYMBOL_LINES)):
        text = re.sub(r"""(["'`])(?:\\.|(?!\1).)*\1|//.*$""", "", lines[j])
        for ch in text:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
        if opened and depth <= 0:
            return j
        if not opened and j - i >= 3:
            break
    # No block: an arrow returning an expression, or a one-line definition. It ends at a blank line or a `;`.
    for j in range(i, min(len(lines), i + ARROW_BODY_LINES)):
        if j > i and not lines[j].strip():
            return j - 1
        if lines[j].rstrip().endswith(";"):
            return j
    return min(len(lines) - 1, i + ARROW_BODY_LINES - 1)


def _brace_symbols(path: str, lines: list[str]) -> list[Symbol]:
    out: list[Symbol] = []
    for i, line in enumerate(lines):
        route = _JS_ROUTE.match(line)
        if route:
            out.append(Symbol(path, f"{route.group(1)} {route.group(2)}", "route", i + 1, _brace_end(lines, i) + 1))
            continue
        for pattern in _BRACE_DEFS:
            m = pattern.match(line)
            if m and m.group(1) not in _NOT_NAMES:
                kind = "class" if re.search(r"\b(class|interface|struct|enum|trait|impl)\b", line) else "function"
                out.append(Symbol(path, m.group(1), kind, i + 1, _brace_end(lines, i) + 1))
                break
    return out


def symbols(path: str, text: str) -> list[Symbol]:
    """Functions, classes, components and routes in one file, each with its line range, plus the whole file when it is short."""
    lines = text.splitlines()
    if not lines:
        return []
    suffix = PurePosixPath(path).suffix.lower()
    found = _python_symbols(path, lines) if suffix == ".py" else ([] if suffix in _WHOLE_FILE_SUFFIXES else _brace_symbols(path, lines))
    if suffix in _WHOLE_FILE_SUFFIXES or len(lines) <= WHOLE_FILE_LINES:
        p = PurePosixPath(path)
        found.append(Symbol(path, p.stem + " " + " ".join(p.parent.parts[-2:]), "file", 1, min(len(lines), MAX_SYMBOL_LINES)))
    return found
