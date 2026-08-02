"""Storage contracts for LizardCare event history."""

from __future__ import annotations

from typing import Protocol

from .models import LizardCareEvent


class EventStore(Protocol):
    """Persistence boundary for reptile event history."""

    async def async_append_event(self, event: LizardCareEvent) -> None:
        """Persist one event."""
        ...

    async def async_list_events(
        self, *, reptile_id: str | None = None
    ) -> tuple[LizardCareEvent, ...]:
        """Return events, optionally filtered to one reptile."""
        ...


class NullEventStore:
    """Non-persistent store used until event persistence is introduced."""

    async def async_append_event(self, event: LizardCareEvent) -> None:
        """Accept an event without persisting it."""

    async def async_list_events(
        self, *, reptile_id: str | None = None
    ) -> tuple[LizardCareEvent, ...]:
        """Return an empty event history."""
        return ()
