"""One Browserless BrowserQL (BQL) request on the stealth endpoint, with a residential proxy and human-like input."""
from __future__ import annotations

from typing import Optional

import httpx


class BqlError(RuntimeError):
    """Browserless failed or answered with BQL errors: "could not check", never a verdict on anyone."""


def run_bql(bql_url: str, token: str, query: str, variables: dict, *, http: Optional[httpx.Client] = None) -> dict:
    params = {"token": token, "proxy": "residential", "humanlike": "true", "blockConsentModals": "true"}
    try:
        response = (http or httpx.Client(timeout=300)).post(bql_url.rstrip("/"), params=params,
                                                            json={"query": query, "variables": variables})
    except httpx.TransportError as err:
        raise BqlError(f"browserless unreachable: {err}") from err
    if response.status_code != 200:
        raise BqlError(f"browserless answered {response.status_code}: {response.text[:200]}")
    body = response.json()
    if body.get("errors"):
        raise BqlError("; ".join(e.get("message", "?") for e in body["errors"])[:300])
    return body["data"]
