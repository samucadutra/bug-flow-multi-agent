import pytest

from bugflow.services import run_events
from bugflow.services.errors import NotFoundError
from bugflow.services.run_events import EventPage, follow_pages, iter_run_events


def page(cursor, finished=False, events=()):
    return EventPage.model_construct(events=list(events), cursor=cursor, finished=finished)


def test_sleeps_between_pages_and_not_after_the_final_one():
    pages = iter([page("a"), page("b"), page("c", finished=True)])
    cursors, sleeps = [], []

    def read(cursor):
        cursors.append(cursor)
        return next(pages)

    assert list(follow_pages(read, None, 0.5, sleeps.append)) == []
    assert sleeps == [0.5, 0.5]
    assert cursors == [None, "a", "b"]


def test_a_finished_first_page_ends_without_sleeping():
    sleeps = []
    assert list(follow_pages(lambda c: page("x", True), None, 0.5, sleeps.append)) == []
    assert sleeps == []


def test_events_are_yielded_before_sleeping():
    log = []
    pages = iter([page("a", events=["e1"]), page("b", True, events=["e2"])])

    def sleep(seconds):
        log.append("sleep")

    for event in follow_pages(lambda c: next(pages), None, 0.5, sleep):
        log.append(event)
    assert log == ["e1", "sleep", "e2"]


def test_closing_mid_run_stops_after_the_current_page():
    reads = []

    def read(cursor):
        reads.append(cursor)
        return page(f"c{len(reads)}", events=[len(reads)])

    generator = follow_pages(read, None, 0.5, lambda s: None)
    assert next(generator) == 1 and next(generator) == 2
    generator.close()
    assert len(reads) == 2


def test_default_interval_is_half_a_second():
    assert run_events.POLL_INTERVAL_SECONDS == 0.5


def test_iter_run_events_validates_eagerly(monkeypatch):
    def unknown(engine, run_id, after=None):
        raise NotFoundError(f"Run {run_id} not found")

    monkeypatch.setattr(run_events, "read_run_events", unknown)
    with pytest.raises(NotFoundError, match="Run 5 not found"):
        iter_run_events(object(), 5)


def test_iter_run_events_uses_the_injected_sleep_and_interval(monkeypatch):
    pages = iter([page("a"), page("b", True)])
    monkeypatch.setattr(run_events, "read_run_events", lambda e, r, a=None: next(pages))
    sleeps = []
    assert list(iter_run_events(object(), 1, poll_interval=0.25, sleep=sleeps.append)) == []
    assert sleeps == [0.25]
