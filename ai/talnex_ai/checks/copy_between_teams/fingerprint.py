"""A fingerprint of a repository's code that survives renaming: comments and spacing are dropped, every name becomes "I", every
number "N" and every string "S", and the remaining shape (keywords, brackets, operators) is cut into overlapping runs of tokens
that are hashed. Two repos that share logic share many hashes even when every variable was renamed.

This file uses ONLY the Python standard library on purpose: the same file is sent into a throwaway VM and run there on the cloned
repository (`python3 - <dir>`), and the worker imports it too, so the tests run exactly what the VM runs.
Output is one JSON object: {"files": {path: [hash, ...]}, "skipped": n}.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".html", ".htm", ".py", ".rb", ".php", ".go", ".java",
                 ".kt", ".cs", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".dart", ".ejs", ".hbs", ".pug"}
SKIPPED_PARTS = {"node_modules", "vendor", "dist", "build", ".next", "out", "target", "__pycache__", ".venv", "venv", "coverage",
                 "migrations", "fixtures", "third_party", "bower_components", "site-packages"}
SKIPPED_NAMES = re.compile(r"(\.min\.|\.bundle\.|\.d\.ts$|-lock\.|\.lock$|\.map$|^package-lock|^yarn\.lock)")
MAX_FILE_BYTES = 200_000
MAX_FILES = 400
RUN = 8            # tokens per shingle
KEEP_EVERY = 3     # keep a hash when its number is a multiple of this (a stable sample, so two repos keep the same ones)
MIN_TOKENS = 40    # a file shorter than this says too little to compare

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/|<!--.*?-->", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?m)(^|[^:\"'\w])(//[^\n]*)")
_HASH_COMMENT = re.compile(r"(?m)^\s*#[^\n]*|\s#\s[^\n]*")
_TOKEN = re.compile(r"""[A-Za-z_$][\w$]*|\d[\w.]*|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`|=>|==+|!=+|<=|>=|&&|\|\||\+\+|--|[^\s\w]""")
KEYWORDS = frozenset("""
if else elif for while do switch case break continue return function def class new this self super import from export default const let var
async await try catch except finally throw raise with as yield in of is not and or typeof instanceof delete void null true false None
True False undefined lambda pass global static public private protected interface extends implements enum type struct func go defer
chan range package use fn impl match mut pub crate
""".split())


def normalise(text: str, suffix: str) -> list[str]:
    """The tokens of a source file with names, numbers and strings made anonymous and comments removed."""
    text = _BLOCK_COMMENT.sub(" ", text)
    if suffix in (".py", ".rb"):
        text = _HASH_COMMENT.sub(" ", text)
    else:
        text = _LINE_COMMENT.sub(r"\1 ", text)
    out: list[str] = []
    for tok in _TOKEN.findall(text):
        c = tok[0]
        if c in "\"'`":
            out.append("S")
        elif c.isdigit():
            out.append("N")
        elif c.isalpha() or c in "_$":
            out.append(tok if tok in KEYWORDS else "I")
        else:
            out.append(tok)
    return out


def shingles(tokens: list[str], run: int = RUN) -> list[int]:
    """Sampled hashes of every run of `run` tokens in a row."""
    if len(tokens) < max(run, MIN_TOKENS):
        return []
    hashes: set[int] = set()
    for i in range(len(tokens) - run + 1):
        h = int.from_bytes(hashlib.md5(" ".join(tokens[i:i + run]).encode()).digest()[:4], "big")
        if h % KEEP_EVERY == 0:
            hashes.add(h)
    return sorted(hashes)


def fingerprint_text(text: str, suffix: str) -> list[int]:
    return shingles(normalise(text, suffix))


def wanted(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    return (os.path.splitext(name)[1].lower() in CODE_SUFFIXES and not (set(p.lower() for p in parts[:-1]) & SKIPPED_PARTS)
            and not SKIPPED_NAMES.search(name.lower()))


def fingerprint_repo(root: str) -> dict:
    listing = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, timeout=60).stdout.splitlines()
    files: dict[str, list[int]] = {}
    skipped = 0
    for path in listing:
        if not wanted(path):
            continue
        full = os.path.join(root, path)
        try:
            if os.path.getsize(full) > MAX_FILE_BYTES or len(files) >= MAX_FILES:
                skipped += 1
                continue
            with open(full, encoding="utf-8", errors="replace") as fh:
                hashes = fingerprint_text(fh.read(), os.path.splitext(path)[1].lower())
        except OSError:
            skipped += 1
            continue
        if hashes:
            files[path] = hashes
    return {"files": files, "skipped": skipped}


if __name__ == "__main__":
    print(json.dumps(fingerprint_repo(sys.argv[1] if len(sys.argv) > 1 else ".")))
