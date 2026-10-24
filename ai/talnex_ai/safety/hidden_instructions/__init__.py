"""Finds text aimed at an AI checker: hidden or tiny text, and phrases that try to give a model orders.

This only gathers evidence for a flag (architecture section 17, "Hidden AI instructions": Strong
when the text is hidden). It never decides a verdict, and the text is never obeyed.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable, Optional

# Phrases that speak to an AI reviewer rather than to a human visitor.
_ORDERS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)",
    r"disregard (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)",
    r"(?:you are|act as) (?:now )?(?:an? )?(?:ai|llm|language model|assistant|evaluator|judge|reviewer|grader)",
    r"(?:mark|rate|score|grade|label) (?:this|the) (?:project|app|site|submission|feature|claim|result)s? "
    r"(?:as )?(?:verified|working|passed|perfect|excellent|10/10|full marks)",
    r"give (?:this|the) (?:project|app|site|submission) (?:a )?(?:perfect|full|maximum|top|high|10/10)",
    r"(?:system|developer) prompt",
    r"do not (?:flag|report|mention|penali[sz]e|deduct)",
    r"(?:note|message|instruction)s? (?:to|for) (?:the )?(?:ai|llm|model|evaluator|judge|reviewer|grader|checker)",
    r"if you are an? (?:ai|llm|language model|automated)",
    r"reveal (?:your|the) (?:system )?(?:prompt|instructions)",
]
_ORDER_RE = re.compile("|".join(f"(?:{p})" for p in _ORDERS), re.IGNORECASE)

# Inline styles that make text invisible, tiny or pushed off screen.
_HIDING_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\b|font-size\s*:\s*0(?:px|em|rem|pt)?\b|"
    r"font-size\s*:\s*[0-1](?:\.\d+)?px|(?:left|top|text-indent)\s*:\s*-\d{3,}|"
    r"height\s*:\s*0(?:px)?\b[^;]*overflow\s*:\s*hidden|clip\s*:\s*rect\(\s*0",
    re.IGNORECASE,
)
_VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "area", "base", "col", "embed", "wbr", "track"}
LONG_HIDDEN_WORDS = 12

LEVELS = {"strong": 3, "review": 2, "info": 1}


@dataclass(frozen=True)
class Finding:
    kind: str     # hidden_order, visible_order or hidden_text
    level: str    # strong, review or info
    snippet: str  # what was found, shortened

    def as_flag_evidence(self) -> dict:
        return {"kind": self.kind, "snippet": self.snippet}


def normalise(text: str) -> str:
    """Undo the tricks used to slip an order past a word filter: invisible zero-width characters,
    look-alike letters (fullwidth and similar forms), and runs of spaces or new lines."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")  # zero-width spaces, joiners, BOMs
    return " ".join(text.split())


class _Scan(HTMLParser):
    """Collects each piece of text with whether it sits inside something hidden."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open_tags: list[tuple[str, bool]] = []  # (tag, hides its content)
        self.pieces: list[tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag in _VOID_TAGS:
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        hides = ("hidden" in attr or attr.get("aria-hidden", "").lower() == "true"
                 or bool(_HIDING_STYLE.search(attr.get("style", ""))))
        self.open_tags.append((tag, hides))

    def handle_endtag(self, tag) -> None:
        # Close the nearest matching tag, and anything left open inside it (sloppy HTML is common).
        for i in range(len(self.open_tags) - 1, -1, -1):
            if self.open_tags[i][0] == tag:
                del self.open_tags[i:]
                return

    def handle_comment(self, data) -> None:
        self.pieces.append((data, True))  # a visitor never sees comments

    def handle_data(self, data) -> None:
        if data.strip():
            self.pieces.append((data, any(hides for _, hides in self.open_tags)))


def _short(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def find_hidden_instructions(content: str) -> list[Finding]:
    """Scan HTML, or plain text such as a README, for text aimed at an AI checker."""
    scan = _Scan()
    try:
        scan.feed(content)
        scan.close()
    except Exception:  # badly broken markup must not stop the check: fall back to the plain text
        scan.pieces = []
    pieces = scan.pieces or [(content, False)]

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for raw, hidden in pieces:
        text = normalise(raw)
        if _ORDER_RE.search(text):
            kind, level = ("hidden_order", "strong") if hidden else ("visible_order", "review")
        elif hidden and len(text.split()) >= LONG_HIDDEN_WORDS:
            kind, level = "hidden_text", "info"  # a long hidden paragraph: worth a look, not strong evidence
        else:
            continue
        snippet = _short(text)
        if (kind, snippet) not in seen:
            seen.add((kind, snippet))
            findings.append(Finding(kind, level, snippet))
    return findings


def strongest(findings: Iterable[Finding]) -> Optional[str]:
    """The highest level among the findings: strong, review, info, or None."""
    return max((f.level for f in findings), key=LEVELS.__getitem__, default=None)
