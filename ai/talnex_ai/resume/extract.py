"""Turns a resume PDF into plain text. Nothing here keeps the file or the text: callers use it and drop it."""
from __future__ import annotations

import io
import re

import pdfplumber

MAX_PAGES = 6
MAX_CHARS = 20_000
MIN_CHARS = 40
MAX_BYTES = 5 * 1024 * 1024
MAX_LINKS = 40
LINKS_HEADING = "Links in the file (words on the page -> address):"


class ResumeError(ValueError):
    """The file cannot be read as a resume. The message says why, in words a recruiter can act on."""


_CID = re.compile(r"\(cid:\d+\)")        # glyphs the PDF could not map to text (often bullet points)
_SPACES = re.compile(r"[ \t\f\v]+")


def looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def pdf_text(data: bytes) -> str:
    """The text of a PDF, cleaned. Raises ResumeError if it is not a PDF or has no readable text."""
    if len(data) > MAX_BYTES:
        raise ResumeError("the resume file is larger than 5 MB")
    if not looks_like_pdf(data):
        raise ResumeError("the file is not a PDF")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages[:MAX_PAGES]]
            links = _page_links(pdf.pages[:MAX_PAGES])
    except Exception as exc:
        raise ResumeError("the PDF could not be opened") from exc

    text = "\n".join(pages)
    text = _CID.sub("-", text)
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < MIN_CHARS:
        raise ResumeError("this PDF has no readable text (is it a scan or a picture?)")
    text = text[:MAX_CHARS]
    if links:
        listed = "\n".join(f"{anchor or 'link'} -> {url}" for anchor, url in links)
        text += f"\n\n{LINKS_HEADING}\n{listed}"
    return text


def _page_links(pages) -> list[tuple[str, str]]:
    """The clickable links of the pages with the words they sit on. A resume often shows only "GitHub" or "Live demo"
    and keeps the address behind the words, so the address would otherwise never be read."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page in pages:
        for link in page.hyperlinks:
            url = str(link.get("uri") or "").strip()
            if not url.lower().startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            anchor = ""
            try:
                box = (max(link["x0"], 0), max(link["top"], 0), min(link["x1"], page.width), min(link["bottom"], page.height))
                anchor = re.sub(r"\s+", " ", page.crop(box).extract_text() or "").strip()[:60]
            except Exception:  # the address is still worth keeping without its words
                pass
            found.append((anchor, url))
            if len(found) == MAX_LINKS:
                return found
    return found
