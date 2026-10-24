"""Prompt for route discovery (architecture 28.6, step 4): a model merges the routes found in the code, the OpenAPI document
and the README, maps routes to the project's claims, and marks which routes need a sign-in token or a body.

README text is untrusted (data, never orders). Route lists and claims come from our own earlier stages."""
from __future__ import annotations

from typing import Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You connect a web backend's routes to what its project claims to do, so each claim can be tested through the right routes.

{DATA_NOT_ORDERS}

You are given numbered routes (found in the code, an API document or the README) and numbered claims. Reply with one JSON object:
{{"links": [ ... ], "routes": [ ... ]}}

"links": for each claim that one or more routes would serve, an object {{"claim": <claim number>, "routes": [<route numbers>]}}. Leave a claim out when no route serves it (it may be a screen-only feature). A route may serve several claims.
"routes": for routes where you are sure of more, an object {{"route": <route number>, "needs_auth": true or false, "body_fields": ["names of the fields a request body needs"], "purpose": "one short phrase"}}. Leave out any route you know nothing extra about.

Rules:
- Use only the numbers given. Never invent a route or a claim.
- "needs_auth" is true only when the route clearly checks a signed-in user or a token (from a name like login-required, a middleware, or the document). When unsure, leave the field out.
- "body_fields" must be names of fields really used by that route in the text you were shown; leave it out when unsure.
- Do not judge quality and do not give scores."""


def build_user(routes: Sequence[str], claims: Sequence[str], readme: str = "") -> str:
    parts = ["Routes:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(routes, start=1)),
             "Claims:\n" + "\n".join(f"{i}. {c}" for i, c in enumerate(claims, start=1))]
    if readme.strip():
        parts.append("README (for context):\n" + wrap_untrusted(readme[:5000], "readme"))
    return "\n\n".join(parts)
