"""Hidden text from a page as the browser really rendered it.

Fetching a page as plain text drops exactly the places where text aimed at an AI checker hides:
comments, elements hidden by a stylesheet, text pushed off screen. The test browser can see them,
so the runner asks it for that text (HIDDEN_TEXT_JS) and this module decides whether any of it
is an order to an AI. Ordinary hidden text (menus, screen-reader labels) is ignored.
"""
from __future__ import annotations

from html import escape
from typing import Iterable

from talnex_ai.safety.hidden_instructions import Finding, find_hidden_instructions

# Runs inside the page. Returns the text of comments and of text a visitor can't see.
HIDDEN_TEXT_JS = """
() => {
  const out = [];
  const seen = new Set();
  const hidden = (el) => {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0 || parseFloat(s.fontSize) < 2) return true;
      const r = e.getBoundingClientRect();
      if (r.width === 0 && r.height === 0 && s.overflow !== 'visible') return true;
      if (r.right < 0 || r.bottom < 0) return true;
    }
    return false;
  };
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_COMMENT);
  while (walker.nextNode() && out.length < 40) {
    const node = walker.currentNode;
    const text = (node.nodeValue || '').replace(/\\s+/g, ' ').trim();
    if (text.length < 12 || seen.has(text)) continue;
    const parent = node.parentElement;
    if (parent && ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(parent.tagName)) continue;
    if (node.nodeType === Node.COMMENT_NODE || (parent && hidden(parent))) {
      seen.add(text);
      out.push(text.slice(0, 400));
    }
  }
  return out;
}
"""


def orders_in_hidden_text(pieces: Iterable[str]) -> list[Finding]:
    """The pieces that are orders to an AI reviewer. Every piece counts as hidden, since that's where it came from."""
    html = "".join(f'<span style="display:none">{escape(p)}</span>' for p in pieces)
    return [f for f in find_hidden_instructions(html) if f.kind == "hidden_order"]
