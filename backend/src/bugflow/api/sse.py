"""Server-Sent Events helper: frame format and a byte generator over the run event source."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from bugflow.services.run_events import LogEvent, RunStatusEvent, StepEvent

RunEventModel = StepEvent | LogEvent | RunStatusEvent

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
SSE_MEDIA_TYPE = "text/event-stream; charset=utf-8"


def format_event(event: RunEventModel) -> str:
    """`id`, `event` and `data` lines followed by a blank line."""
    return f"id: {event.cursor}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"


def resolve_cursor(after: str | None, last_event_id: str | None) -> str | None:
    """The `after` query parameter wins over the `Last-Event-ID` header."""
    return after if after is not None else last_event_id


def frames(events: Iterable[RunEventModel]) -> Iterator[bytes]:
    for event in events:
        yield format_event(event).encode()
