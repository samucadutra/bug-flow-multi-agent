import pytest

from bugflow.services.errors import EmptySearchTextError, ValidationFailedError
from bugflow.services.similarity import (
    DEFAULT_SEARCH_LIMIT,
    search_similar,
    similar_to_bug,
    validate_search,
)


def fields(exc: ValidationFailedError) -> dict[str, str]:
    return {error.field: error.message for error in exc.field_errors}


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_blank_text_raises_the_exact_message(text):
    with pytest.raises(EmptySearchTextError) as caught:
        validate_search(text, 5)
    assert str(caught.value) == "Search text must not be empty"


def test_over_long_text_gives_a_field_error_on_text():
    with pytest.raises(ValidationFailedError) as caught:
        validate_search("a" * 501, 5)
    assert list(fields(caught.value)) == ["text"]


@pytest.mark.parametrize("limit", [0, 21, -1])
def test_limit_outside_range_gives_a_field_error_on_limit(limit):
    with pytest.raises(ValidationFailedError) as caught:
        validate_search("x", limit)
    assert fields(caught.value) == {"limit": "must be between 1 and 20"}


@pytest.mark.parametrize("limit", [1, 20])
def test_limit_bounds_accepted(limit):
    assert validate_search("  x ", limit) == "x"


def test_default_limit_is_five():
    assert DEFAULT_SEARCH_LIMIT == 5
    assert validate_search("a" * 500, DEFAULT_SEARCH_LIMIT) == "a" * 500


def test_validation_precedes_any_client_call():
    def forbidden():
        raise AssertionError("client must not be built")

    for args in (("  ", 5), ("x", 21), ("a" * 501, 5)):
        with pytest.raises((EmptySearchTextError, ValidationFailedError)):
            search_similar(None, forbidden, *args)
    with pytest.raises(ValidationFailedError):
        similar_to_bug(None, forbidden, 1, 21)
