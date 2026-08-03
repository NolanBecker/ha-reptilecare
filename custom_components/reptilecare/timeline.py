"""Reusable queries over immutable ReptileCare CareEvent history."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .models import CareEvent, CareEventType


class Timeline:
    """Provide deterministic read-only queries over CareEvent history."""

    def __init__(self, events: Iterable[CareEvent] = ()) -> None:
        """Initialize a timeline in chronological order."""
        self._events = tuple(
            sorted(events, key=lambda event: (event.timestamp, event.event_id.int))
        )

    def all_events(self) -> tuple[CareEvent, ...]:
        """Return every event in chronological order."""
        return self._events

    def latest_event(self) -> CareEvent | None:
        """Return the most recent event, if one exists."""
        return self._events[-1] if self._events else None

    def latest_event_of_type(
        self,
        event_type: CareEventType,
        *,
        reptile_id: str | None = None,
    ) -> CareEvent | None:
        """Return the most recent matching event."""
        return next(
            (
                event
                for event in reversed(self._events)
                if event.event_type is event_type
                and (reptile_id is None or event.reptile_id == reptile_id)
            ),
            None,
        )

    def events_for_reptile(self, reptile_id: str) -> tuple[CareEvent, ...]:
        """Return all events belonging to one reptile."""
        return tuple(event for event in self._events if event.reptile_id == reptile_id)

    def events_between(
        self,
        start: datetime,
        end: datetime,
        *,
        reptile_id: str | None = None,
    ) -> tuple[CareEvent, ...]:
        """Return events in the inclusive UTC-aware interval."""
        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("timeline bounds must be timezone-aware")
        if start > end:
            raise ValueError("timeline start must not be after end")
        return tuple(
            event
            for event in self._events
            if start <= event.timestamp <= end
            and (reptile_id is None or event.reptile_id == reptile_id)
        )

    def event_count(
        self,
        *,
        reptile_id: str | None = None,
        event_type: CareEventType | None = None,
    ) -> int:
        """Count events matching optional reptile and type filters."""
        return sum(
            1
            for event in self._events
            if (reptile_id is None or event.reptile_id == reptile_id)
            and (event_type is None or event.event_type is event_type)
        )
