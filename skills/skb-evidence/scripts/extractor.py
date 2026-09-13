#!/usr/bin/env python3
"""HTML → plain text extractor using stdlib html.parser.

Removes script/style/nav/header/footer/aside elements.
Returns clean body text with whitespace normalized.
"""

from __future__ import annotations

from html.parser import HTMLParser


_SKIP_TAGS = frozenset({"script", "style", "nav", "header", "footer", "aside"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._depth: list[str] = []   # tag stack
        self._skip_depth: int = 0     # nesting inside skip tags
        self._title: list[str] = []
        self._in_title: bool = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag_lower = tag.lower()
        self._depth.append(tag_lower)
        if tag_lower in _SKIP_TAGS:
            self._skip_depth += 1
        if tag_lower == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._depth and self._depth[-1] == tag_lower:
            self._depth.pop()
        if tag_lower in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag_lower == "title":
            self._in_title = False
        # Insert newline after block elements for readability
        if tag_lower in ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                          "tr", "td", "th", "blockquote", "pre", "section", "article"):
            self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self._title.append(data)
        self._buf.append(data)

    @property
    def title(self) -> str:
        return "".join(self._title).strip()

    @property
    def text(self) -> str:
        raw = "".join(self._buf)
        # Normalize: collapse multiple blank lines, trim edges
        import re
        raw = re.sub(r"\r\n", "\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def extract_html(html_bytes: bytes) -> tuple[str, str]:
    """Return (title, plain_text) from raw HTML bytes."""
    # Detect encoding from meta charset or default to utf-8
    import re
    charset_match = re.search(
        rb'charset=["\']?([a-zA-Z0-9_-]+)', html_bytes[:2048]
    )
    encoding = "utf-8"
    if charset_match:
        encoding = charset_match.group(1).decode("ascii", errors="replace").lower()
    try:
        html_str = html_bytes.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html_str = html_bytes.decode("utf-8", errors="replace")

    parser = _TextExtractor()
    parser.feed(html_str)
    return parser.title, parser.text


def extract_text(content: bytes, content_type: str = "") -> tuple[str, str]:
    """Dispatch: HTML vs plain text. Returns (title, text)."""
    ct = content_type.lower()
    if "html" in ct or content[:200].lstrip()[:5].lower() in (b"<!doc", b"<html"):
        return extract_html(content)
    # plain text / markdown
    text = content.decode("utf-8", errors="replace")
    return "", text
