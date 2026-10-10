"""Markdown, fenced block and Mermaid escaping."""

from __future__ import annotations

import pytest

from bugflow.reports.escape import (
    MERMAID_ENCODED,
    decode_mermaid_label,
    md,
    md_block,
    mermaid_label,
)

MD_SPECIAL = "\\`*_[]<>|~"


@pytest.mark.parametrize("char", list(MD_SPECIAL))
def test_md_escapes_the_fixed_character_set(char: str) -> None:
    assert md(f"a{char}b") == f"a\\{char}b"


def test_md_escapes_ampersand_as_entity() -> None:
    assert md("a & b") == "a &amp; b"


def test_md_collapses_whitespace_and_newlines() -> None:
    assert md("  one\n\n two\t three  ") == "one two three"


def test_md_leaves_quotes_and_plain_text_alone() -> None:
    text = "He said \"hi\" and 'bye', 100% (ok): #1, a/b!"
    assert md(text) == text


def test_md_pipe_cannot_split_a_table_cell() -> None:
    row = f"| Notes | {md('a | b | c')} |"
    assert row == "| Notes | a \\| b \\| c |"
    assert row.replace("\\|", "").count("|") == 3


@pytest.mark.parametrize("run", [0, 2, 3, 5])
def test_md_block_fence_longer_than_any_backtick_run(run: int) -> None:
    text = f"before {'`' * run} after" if run else "plain"
    block = md_block(text)
    fence = "`" * max(3, run + 1)
    lines = block.split("\n")
    assert lines[0] == f"{fence}text"
    assert lines[-1] == fence
    assert text in block
    assert block == f"{fence}text\n{text}\n{fence}"


@pytest.mark.parametrize("char", sorted(MERMAID_ENCODED))
def test_mermaid_label_encodes_the_metacharacter_set(char: str) -> None:
    encoded = mermaid_label(f"a{char}b")
    assert encoded == f"a#{ord(char)};b"
    assert char not in encoded.replace(f"#{ord(char)};", "") or char == "#"


def test_mermaid_label_specification_example() -> None:
    title = 'Crash on `save` | <b>bold</b> says "no"'
    assert mermaid_label(title) == (
        "Crash on #96;save#96; #124; #60;b#62;bold#60;/b#62; says #34;no#34;"
    )


def test_mermaid_label_round_trip() -> None:
    text = 'Won\'t fix #1; <a> | "q" {x} (y) [z] 100% & `c`'
    assert decode_mermaid_label(mermaid_label(text)) == text


def test_mermaid_label_controls_become_spaces() -> None:
    encoded = mermaid_label("a\tb\nc\x00d\x7fe")
    assert encoded == "a b c d e"
    assert all(ord(char) >= 32 and ord(char) != 127 for char in encoded)
