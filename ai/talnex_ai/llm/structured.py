"""Ask a model for a JSON answer, check it, and give it one chance to fix a bad one.

We never guess what a model meant. The answer is validated; if it's wrong, one repair call
shows the model its mistake; if that's also wrong, the stage fails with a clear error and the
claim ends up "could not test", never with an invented result.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, TypeVar

from talnex_ai.formats import FormatError

log = logging.getLogger("talnex.llm")

T = TypeVar("T")

JSON_MODE = {"type": "json_object"}


class ChatClient(Protocol):
    """What this helper needs from a model client. Both provider clients fit."""

    def chat(self, role: str, messages: Sequence[Mapping[str, Any]], **kwargs: Any) -> Any: ...


class StructuredError(RuntimeError):
    """The model didn't give a valid answer, even after one repair try."""


def image_type(data: bytes) -> str:
    """Tell PNG, JPEG, WebP and GIF apart by their first bytes, so each picture is labelled correctly."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    raise ValueError("unsupported image: only PNG, JPEG, WebP and GIF can be sent to a model")


def user_message(text: str, images: Sequence[bytes] = ()) -> dict[str, Any]:
    """A user message, with screenshots attached as pictures when there are any."""
    if not images:
        return {"role": "user", "content": text}
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image in images:
        encoded = base64.b64encode(image).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{image_type(image)};base64,{encoded}"}})
    return {"role": "user", "content": parts}


def ask_json(
    client: ChatClient,
    role: str,
    system: str,
    user: str,
    parse: Callable[[str], T],
    *,
    job_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    images: Sequence[bytes] = (),
) -> T:
    """Send one request and return the parsed answer.

    `parse` turns the answer text into the wanted shape and raises FormatError when it can't."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, user_message(user, images)]
    options: dict[str, Any] = {"job_id": job_id, "response_format": JSON_MODE}
    if max_tokens is not None:
        options["max_tokens"] = max_tokens
    if temperature is not None:
        options["temperature"] = temperature

    first = client.chat(role, messages, **options)
    try:
        return parse(first.text)
    except FormatError as first_error:
        problem = first_error
        cut_off = bool(getattr(first, "truncated", False))

    log.warning("the %s answer was not valid (%s); asking for one repair", role, problem)
    if cut_off:
        # A cut-off answer isn't a mistake the model can "fix"; it just ran out of room.
        note = "Your answer was cut off before it finished. Reply again with the complete JSON, keeping text fields short."
        if max_tokens is not None:
            options["max_tokens"] = max_tokens * 2
    else:
        note = f"That answer was not valid: {problem}. Reply again with only the corrected JSON, in exactly the format asked for."
    repair = messages + [{"role": "assistant", "content": first.text}, {"role": "user", "content": note}]

    second = client.chat(role, repair, **options)
    try:
        return parse(second.text)
    except FormatError as second_error:
        raise StructuredError(
            f"the {role} model did not give a valid answer after one repair try: {second_error}"
        ) from second_error
