import pytest

from bugflow.services.errors import ValidationFailedError
from bugflow.services.schemas import BugListQuery, SortBy, SortDir, validate_payload


def test_defaults():
    query = BugListQuery()
    assert (query.sort_by, query.sort_dir, query.page, query.page_size) == (
        SortBy.OPENED_AT,
        SortDir.DESC,
        1,
        20,
    )
    assert query.search is None


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"page": 0}, "page"),
        ({"page_size": 0}, "page_size"),
        ({"page_size": 101}, "page_size"),
        ({"sort_by": "title"}, "sort_by"),
        ({"sort_dir": "up"}, "sort_dir"),
        ({"status": "done"}, "status"),
        ({"search": "x" * 201}, "search"),
    ],
)
def test_invalid_values_name_the_field(payload, field):
    with pytest.raises(ValidationFailedError) as caught:
        validate_payload(BugListQuery, payload)
    assert [e.field for e in caught.value.field_errors] == [field]


def test_max_page_size_accepted():
    assert BugListQuery(page_size=100).page_size == 100


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_search_normalized_to_none(blank):
    assert BugListQuery(search=blank).search is None
