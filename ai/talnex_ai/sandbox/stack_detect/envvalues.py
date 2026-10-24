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


# Connection settings for the backing stores the sandbox can start (host = the service's name on the private network).
# These mirror sandboxd's ServiceCatalog; they replace the harmless fakes when a service is actually running beside the VM.
SERVICE_ENV: dict[str, dict[str, str]] = {
    "postgres": {
        "DATABASE_URL": "postgres://talnex:talnex@postgres:5432/talnex",
        "POSTGRES_URL": "postgres://talnex:talnex@postgres:5432/talnex",
        "POSTGRES_HOST": "postgres", "POSTGRES_PORT": "5432", "POSTGRES_USER": "talnex",
        "POSTGRES_PASSWORD": "talnex", "POSTGRES_DB": "talnex",
        "PGHOST": "postgres", "PGPORT": "5432", "PGUSER": "talnex", "PGPASSWORD": "talnex", "PGDATABASE": "talnex",
    },
    "redis": {"REDIS_URL": "redis://redis:6379", "REDIS_HOST": "redis", "REDIS_PORT": "6379"},
    "mongodb": {"MONGO_URL": "mongodb://mongodb:27017", "MONGODB_URI": "mongodb://mongodb:27017",
                "MONGO_HOST": "mongodb", "MONGO_PORT": "27017"},
}


def service_env(services) -> dict[str, str]:
    """Real connection settings for the services running beside the VM. Unknown services are ignored."""
    env: dict[str, str] = {}
    for service in services or ():
        env.update(SERVICE_ENV.get(service, {}))
    return env
