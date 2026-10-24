"""Plan steps that name one clear action, turned into browser actions by plain code, with no model call.

"type 'milk' into 'What needs to be done?'", "click Add", "press Enter" need no judgement, so the loop does them
directly and only asks the model when a step is anything else, or when the page does not match. The reader is
deliberately strict: a step it does not fully understand returns None and goes to the model as before.

Nothing here knows an app. Names are looked up by what a visitor sees (label, placeholder, role, text).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from talnex_ai.testing.runner.actions import Action, Click, FreshStart, Fill, Press, Select, Target

_QUOTED = re.compile(r"""'([^']+)'|"([^"]+)"|“([^”]+)”|‘([^’]+)’""")
_SPLIT = re.compile(
    r"\s*(?:,\s*)?(?:and then|then|and)\s+(?=(?:type|enter|write|click|tap|press|hit|select|choose|start fresh)\b)"
    r"|\s*,\s*(?=(?:type|enter|write|click|tap|press|hit|select|choose)\b)", re.IGNORECASE)

_KEYS = {"enter": "Enter", "return": "Enter", "tab": "Tab", "escape": "Escape", "esc": "Escape", "space": "Space",
         "backspace": "Backspace", "delete key": "Delete", "arrow down": "ArrowDown", "arrow up": "ArrowUp"}
_OPEN = re.compile(r"^(?:open|go to|visit|load)\s+(?:the\s+)?(?:site|page|app|website|web ?site|home ?page|start page|"
                   r"live site|live link)(?:\s+(?:in (?:a|the) browser|first))?$", re.IGNORECASE)
_FRESH = re.compile(r"^(?:start fresh(?: as a new visitor)?|clear (?:the )?(?:cookies|browser data)(?: and saved data)?)$",
                    re.IGNORECASE)
_NAME = r"(?P<name>\x00\d+\x00|[A-Za-z][A-Za-z0-9 \-/&']{0,60}?)"
_VALUE = r"(?P<value>\x00\d+\x00)"
_FILL = re.compile(rf"^(?:type|enter|write|put)\s+{_VALUE}\s+(?:in|into|in to)\s+(?:the\s+)?{_NAME}"
                   r"(?:\s+(?:field|box|input|textbox|text box|text field|bar))?$", re.IGNORECASE)
_SELECT = re.compile(rf"^(?:select|choose)\s+{_VALUE}\s+(?:in|from)\s+(?:the\s+)?{_NAME}"
                     r"(?:\s+(?:dropdown|drop-down|menu|list|select|field))?$", re.IGNORECASE)
_CLICK = re.compile(rf"^(?:click|tap|press|hit)\s+(?:on\s+)?(?:the\s+)?{_NAME}(?:\s+(?:button|link|tab))?$", re.IGNORECASE)
_PRESS = re.compile(r"^(?:press|hit)\s+(?:the\s+)?(?P<key>[A-Za-z ]{2,12}?)(?:\s+key)?$", re.IGNORECASE)
_NOT_A_NAME = re.compile(r"\b(?:if|until|so|to|that|which|when|where|after|before|each|all|every|any|again|and|or|in|on|of|the|first|second|third|last|next|then|check|click|type|open)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SimpleStep:
    """What a simple step does. No actions means "open the site": the page is already open, so only look."""

    actions: tuple[Action, ...]


def parse_simple_step(text: str) -> Optional[SimpleStep]:
    """The step as direct actions, or None when it is not simple (sign in, check something, anything unclear)."""
    quoted: list[str] = []

    def hide(match: re.Match) -> str:
        quoted.append(next(g for g in match.groups() if g is not None))
        return f"\x00{len(quoted) - 1}\x00"

    flat = _QUOTED.sub(hide, " ".join((text or "").split())).strip().rstrip(".!")
    if not flat:
        return None
    if _OPEN.match(flat):
        return SimpleStep(())
    actions: list[Action] = []
    for clause in _SPLIT.split(flat):
        action = _clause(clause.strip().rstrip(".,"), quoted)
        if action is None:
            return None
        actions.append(action)
    return SimpleStep(tuple(actions)) if actions else None


def _restore(piece: str, quoted: list[str]) -> Optional[str]:
    match = re.fullmatch(r"\x00(\d+)\x00", piece)
    if match:
        return quoted[int(match.group(1))]
    if "\x00" in piece or _NOT_A_NAME.search(piece):
        return None  # a bare phrase with extra words is a sentence, not a name
    return piece.strip() or None


def _clause(clause: str, quoted: list[str]) -> Optional[Action]:
    if _FRESH.match(clause):
        return FreshStart(type="fresh_start")
    key = _PRESS.match(clause)
    if key and key.group("key").lower() in _KEYS:
        return Press(type="press", key=_KEYS[key.group("key").lower()])
    for pattern, build in ((_FILL, "fill"), (_SELECT, "select")):
        match = pattern.match(clause)
        if match:
            value, name = _restore(match.group("value"), quoted), _restore(match.group("name"), quoted)
            if not value or not name or len(value) > 500:
                return None
            target = Target(kind="any", name=name)
            return Fill(type="fill", target=target, value=value) if build == "fill" else \
                Select(type="select", target=target, value=value)
    match = _CLICK.match(clause)
    if match:
        name = _restore(match.group("name"), quoted)
        if name and len(name.split()) <= 5 and "\x00" not in name:
            return Click(type="click", target=Target(kind="any", name=name))
    return None
