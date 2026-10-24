"""Harmless values for the settings a repo's .env.example lists (architecture 28.9).

The repo is never given a real key. A value the author wrote is kept. An empty or placeholder value gets a fake that
fits the setting's name, because an app that reads PORT or MAIL_PORT as a number crashes on the text "placeholder",
and that crash would be our fault, not the project's."""
from __future__ import annotations

import re

_SECRETISH = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|SALT)", re.I)
_NUMBER_WORDS = re.compile(r"(^|_)(TIMEOUT|TTL|SECONDS|MINUTES|HOURS|DAYS|LIMIT|SIZE|COUNT|MAX|MIN|EXPIRE|EXPIRES|EXPIRY|LIFETIME|WORKERS|THREADS|RETRIES|ATTEMPTS|INTERVAL|DURATION)(_|$)", re.I)
_FLAG_WORDS = re.compile(r"^(DEBUG|TESTING|VERBOSE)$|(^|_)(ENABLE|ENABLED|DISABLE|DISABLED|USE|VERIFY|SSL|TLS|SANDBOX|MOCK|DEBUG|STRICT)(_|$)", re.I)
_BLANK = {"", "your_key_here", "changeme", "xxx", "todo", "your-api-key", "your_api_key", "none", "null"}


def placeholder_for(key: str, value: str) -> str:
    """The value to use for one setting: the author's own when it is real, else a fake that fits the name."""
    value = value.strip().strip("'\"")
    if value.lower() not in _BLANK and not value.startswith("<") and not value.startswith("your"):
        return value
    upper = key.upper()
    if upper == "PORT":
        return "3000"
    if upper.endswith("PORT"):
        return "1025"
    if _SECRETISH.search(key):
        return f"talnex-placeholder-{key.lower()}"
    if _FLAG_WORDS.search(upper):
        return "false"
    if _NUMBER_WORDS.search(upper):
        return "60"
    if re.search(r"(URL|URI|ENDPOINT|ORIGIN|ADDRESS)$", upper):
        return "http://localhost"
    if upper.endswith("HOST") or upper.endswith("SERVER"):
        return "localhost"
    if re.search(r"(EMAIL|MAIL_FROM|MAIL_SENDER|SENDER)", upper):
        return "talnex@example.com"
    if re.search(r"(USER|USERNAME|LOGIN)$", upper):
        return "talnex"
    return "placeholder"


def env_placeholders(example_text: str) -> dict[str, str]:
    """{name: value} for every setting an .env.example lists."""
    env: dict[str, str] = {}
    for line in example_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            env[key] = placeholder_for(key, value)
    return env
