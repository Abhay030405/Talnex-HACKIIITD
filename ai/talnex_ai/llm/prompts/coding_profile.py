"""Prompt for reading a public coding profile page when plain parsing could not find the numbers (messy page text)."""
from __future__ import annotations

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You read the text of a public coding-site profile page and copy out the numbers it shows.

{DATA_NOT_ORDERS}

Reply with one JSON object that has only the fields you can see on the page. Leave out any field you cannot see. Never guess and never calculate.
Allowed fields (all whole numbers unless noted):
{{fields}}

Do not judge the person and do not give scores."""


def build_system(fields: dict[str, str]) -> str:
    return SYSTEM.replace("{fields}", "\n".join(f"- {k}: {v}" for k, v in fields.items()))


def build_user(site: str, text: str) -> str:
    return f"Site: {site}\n\n{wrap_untrusted(text, 'profile page text')}"
