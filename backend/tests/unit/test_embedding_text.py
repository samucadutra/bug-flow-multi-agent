from types import SimpleNamespace

from bugflow.services.embeddings import enriched_text, query_text, text_hash


def make_bug(**overrides):
    values = {
        "title": "Checkout button unresponsive",
        "description": "Nothing happens when paying.",
        "reproduction_steps": "Open the cart and pay.",
        "system_version": "web 1.0.0",
        "environment": "production",
        "reporting_team": "support",
        "status": "open",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_enriched_text_has_five_labeled_lines():
    assert enriched_text(make_bug()).split("\n") == [
        "Title: Checkout button unresponsive",
        "Description: Nothing happens when paying.",
        "Steps to reproduce: Open the cart and pay.",
        "System version: web 1.0.0",
        "Environment: production",
    ]


def test_status_team_and_dates_not_in_text():
    base = enriched_text(make_bug())
    assert enriched_text(make_bug(status="failed", reporting_team="qa")) == base


def test_text_changes_with_each_text_field():
    base = make_bug()
    for field in (
        "title",
        "description",
        "reproduction_steps",
        "system_version",
        "environment",
    ):
        changed = make_bug(**{field: "changed value"})
        assert enriched_text(changed) != enriched_text(base)
        assert text_hash("m", enriched_text(changed)) != text_hash("m", enriched_text(base))


def test_hash_depends_on_model():
    text = enriched_text(make_bug())
    first, second = text_hash("model-a", text), text_hash("model-b", text)
    assert first != second
    assert len(first) == 64 and int(first, 16) >= 0


def test_query_text_is_trimmed_input():
    assert query_text("  Checkout  button \n") == "Checkout  button"
