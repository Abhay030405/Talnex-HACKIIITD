"""Turning a model's text answer into a checked shape, or a clear error.

Models are asked for JSON, but they don't always answer with JSON alone: they wrap it in
```json fences, or add "Here is the plan:" in front. We find the JSON, then validate it.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_DECODER = json.JSONDecoder()


class FormatError(ValueError):
    """The answer has no valid JSON, or the JSON doesn't match the expected shape."""


def parse_json_block(text: str) -> Any:
    """Find the JSON value in a model answer.

    Tries, in order: the text as-is, the inside of a ``` fence, then the first place in the
    text where a complete JSON object or list starts."""
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # raw_decode reads one complete JSON value and stops, so trailing words or a second
    # object after it don't break anything.
    for candidate in candidates:
        for start, char in enumerate(candidate):
            if char in "{[":
                try:
                    value, _ = _DECODER.raw_decode(candidate, start)
                    return value
                except json.JSONDecodeError:
                    continue
    raise FormatError("the answer does not contain valid JSON")


def parse_model(model: Type[T], text: str) -> T:
    """Parse the answer into one shape."""
    data = parse_json_block(text)
    try:
        return model.model_validate(data)
    except ValidationError as err:
        raise FormatError(_explain(err)) from err


def parse_list(model: Type[T], text: str, key: Optional[str] = None) -> list[T]:
    """Parse the answer into a list of shapes: a bare list, or an object holding the list under `key`."""
    data = parse_json_block(text)
    if isinstance(data, dict) and key is not None and key in data:
        data = data[key]
    if not isinstance(data, list):
        raise FormatError(f"expected a list{f' under {key!r}' if key else ''}")
    items = []
    for number, item in enumerate(data, start=1):
        try:
            items.append(model.model_validate(item))
        except ValidationError as err:
            raise FormatError(f"item {number}: {_explain(err)}") from err
    return items


def _explain(err: ValidationError) -> str:
    """A short, readable summary of what was wrong (at most five problems), fit to send back to the model."""
    problems = []
    for e in err.errors()[:5]:
        where = ".".join(str(p) for p in e["loc"]) or "answer"
        problems.append(f"{where}: {e['msg']}")
    return "; ".join(problems)
