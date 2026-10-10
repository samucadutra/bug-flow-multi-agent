"""Escaping helpers for Markdown text, fenced blocks and Mermaid labels."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
_BACKTICK_RUN = re.compile(r"`+")
_MD_SPECIAL = frozenset("\\`*_[]<>|~")
MERMAID_ENCODED = frozenset("\"#%&'();<>[]\\`{|}")
_ENTITY = re.compile(r"#(\d+);")


def collapse(text: str) -> str:
    """Collapse every whitespace run (newlines included) to one space and trim."""
    return _WHITESPACE.sub(" ", text).strip()


def md(value: object) -> str:
    """Escape short text for Markdown headings, list items, paragraphs and table cells."""
    text = collapse(str(value)).replace("&", "&amp;")
    return "".join(f"\\{char}" if char in _MD_SPECIAL else char for char in text)


def md_block(value: object) -> str:
    """The text unchanged inside a fenced block whose fence is longer than any backtick run."""
    text = str(value)
    longest = max((len(run) for run in _BACKTICK_RUN.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def mermaid_label(value: object) -> str:
    """Encode text for a double-quoted Mermaid label; metacharacters become `#<code>;`."""
    text = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in str(value))
    text = collapse(text)
    return "".join(f"#{ord(char)};" if char in MERMAID_ENCODED else char for char in text)


def decode_mermaid_label(label: str) -> str:
    """Inverse of `mermaid_label` (for tests): `#<code>;` becomes the character."""
    return _ENTITY.sub(lambda match: chr(int(match.group(1))), label)
