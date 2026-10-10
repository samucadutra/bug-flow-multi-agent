"""Template lint: escaped expressions, no hard-coded resolution, one pinned CDN URL."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, StrictUndefined, UndefinedError

from bugflow.reports.render import MERMAID_VERSION, TEMPLATE_DIR

MARKDOWN = TEMPLATE_DIR / "report.md.j2"
HTML = TEMPLATE_DIR / "report.html.j2"
ALLOWED_FILTERS = {"md", "md_block", "mermaid_block", "iso", "opened", "days", "int"}


def _expressions(path: Path) -> list[str]:
    return [match.strip() for match in re.findall(r"\{\{(.*?)\}\}", path.read_text("utf-8"))]


def test_every_markdown_expression_ends_in_an_allowed_filter() -> None:
    expressions = _expressions(MARKDOWN)
    assert expressions
    for expression in expressions:
        last = expression.rsplit("|", 1)[-1].strip()
        assert last in ALLOWED_FILTERS, expression


@pytest.mark.parametrize("path", [MARKDOWN, HTML], ids=lambda path: path.name)
def test_templates_never_hard_code_a_resolution(path: Path) -> None:
    assert "resolved" not in path.read_text("utf-8").lower()


def test_both_templates_exist() -> None:
    assert MARKDOWN.is_file()
    assert HTML.is_file()


def test_html_template_references_exactly_one_pinned_cdn_url() -> None:
    text = HTML.read_text("utf-8")
    urls = re.findall(r"https?://[^\s\"'<>)]+", text)
    assert len(urls) == 1
    match = re.fullmatch(
        r"https://cdn\.jsdelivr\.net/npm/mermaid@(\d+\.\d+\.\d+)/dist/mermaid\.esm\.min\.mjs",
        urls[0],
    )
    assert match
    assert match.group(1) == MERMAID_VERSION
    assert "@latest" not in text
    assert text.count("<script") == 1


def test_markdown_template_starts_with_a_heading_at_byte_zero() -> None:
    assert MARKDOWN.read_bytes().startswith(b"# ")


def test_strict_undefined_raises_for_a_missing_variable() -> None:
    env = Environment(undefined=StrictUndefined)
    with pytest.raises(UndefinedError):
        env.from_string("{{ missing }}").render()
