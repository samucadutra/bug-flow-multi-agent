import itertools

import pytest

from bugflow.enums import BugStatus
from bugflow.services.bugs import ALLOWED_TRANSITIONS, ensure_transition_allowed
from bugflow.services.errors import StateConflictError

S = BugStatus
ALLOWED = [
    (S.OPEN, S.PROCESSING),
    (S.PROCESSING, S.PROCESSED),
    (S.PROCESSING, S.FAILED),
    (S.PROCESSED, S.OPEN),
    (S.FAILED, S.OPEN),
]
FORBIDDEN = [pair for pair in itertools.product(S, S) if pair not in ALLOWED]


@pytest.mark.parametrize(("current", "new"), ALLOWED)
def test_allowed_pairs(current, new):
    ensure_transition_allowed(current, new)


def test_table_matches_allowed_pairs():
    assert {(c, n) for c, targets in ALLOWED_TRANSITIONS.items() for n in targets} == set(ALLOWED)


@pytest.mark.parametrize(("current", "new"), FORBIDDEN)
def test_forbidden_pairs(current, new):
    with pytest.raises(StateConflictError):
        ensure_transition_allowed(current, new)


def test_message_text():
    with pytest.raises(StateConflictError) as caught:
        ensure_transition_allowed(S.OPEN, S.PROCESSED)
    assert caught.value.message == "Status change from 'open' to 'processed' is not allowed"
