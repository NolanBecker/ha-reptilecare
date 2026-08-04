"""Persistent storage for ReptileCare CareEvent history."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
import logging
from typing import Any, Protocol, cast
from uuid import UUID

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import CareEvent, CareEventType

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 2

type StoredData = dict[str, Any]


class CareEventStore(Protocol):
    """Persistence boundary for reptile CareEvent history."""

    async def async_load(self) -> None:
        """Load persisted events into memory."""
        ...

    async def async_append_event(self, event: CareEvent) -> None:
        """Persist one event."""
        ...

    async def async_get_event(self, event_id: UUID) -> CareEvent | None:
        """Return one persisted event by deterministic identifier."""
        ...

    async def async_list_events(
        self, *, reptile_id: str | None = None
    ) -> tuple[CareEvent, ...]:
        """Return events in chronological order."""
        ...


class _VersionedStore(Store[StoredData]):
    """Home Assistant Store with explicit migration support."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: StoredData,
    ) -> StoredData:
        """Migrate older event payloads to the current schema."""
        return migrate_storage(old_major_version, old_minor_version, old_data)


def migrate_storage(
    old_major_version: int,
    old_minor_version: int,
    old_data: StoredData,
) -> StoredData:
    """Migrate persisted data to the current storage schema."""
    if old_major_version == STORAGE_VERSION:
        if old_minor_version < 2:
            events = old_data.get("events", [])
            return {"events": events if isinstance(events, list) else []}
        return old_data
    if old_major_version == 0:
        events = old_data.get("events", [])
        return {"events": events if isinstance(events, list) else []}
    version = f"{old_major_version}.{old_minor_version}"
    raise ValueError(f"Unsupported ReptileCare storage version {version}")


class HomeAssistantCareEventStore:
    """Event store backed by Home Assistant's versioned Store helper."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize an empty event store for one config entry."""
        self._store = _VersionedStore(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._events: tuple[CareEvent, ...] = ()
        self._write_lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load events, recovering with an empty history if data is corrupt."""
        try:
            stored = await self._store.async_load()
            self._events = _deserialize_events(stored)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Unable to load ReptileCare CareEvent history: %s", err)
            self._events = ()

    async def async_append_event(self, event: CareEvent) -> None:
        """Append one unique event and save the complete history."""
        async with self._write_lock:
            if any(existing.event_id == event.event_id for existing in self._events):
                raise ValueError(f"Duplicate event id: {event.event_id}")
            events = _sort_events((*self._events, event))
            await self._store.async_save(
                {"events": [_serialize_event(item) for item in events]}
            )
            self._events = events

    async def async_get_event(self, event_id: UUID) -> CareEvent | None:
        """Return one event by identifier from the loaded in-memory state."""
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None

    async def async_list_events(
        self, *, reptile_id: str | None = None
    ) -> tuple[CareEvent, ...]:
        """Return events in chronological order, optionally for one reptile."""
        if reptile_id is None:
            return self._events
        return tuple(event for event in self._events if event.reptile_id == reptile_id)


def _sort_events(events: tuple[CareEvent, ...]) -> tuple[CareEvent, ...]:
    """Return events in deterministic chronological order."""
    return tuple(
        sorted(events, key=lambda event: (event.timestamp, event.event_id.int))
    )


def _serialize_event(event: CareEvent) -> StoredData:
    """Convert an event to JSON-compatible storage data."""
    return {
        "event_id": str(event.event_id),
        "reptile_id": event.reptile_id,
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type.value,
        "task_id": event.task_id,
        "care_plan_id": event.care_plan_id,
        "outcome_id": event.outcome_id,
        "context": _json_value(event.context),
        "actor_id": event.actor_id,
        "source": event.source,
        "environmental_snapshot": _json_value(event.environmental_snapshot),
        "attachment_references": list(event.attachment_references),
        "metadata": _json_value(event.metadata),
    }


def _deserialize_events(stored: StoredData | None) -> tuple[CareEvent, ...]:
    """Deserialize and validate a stored event collection."""
    if stored is None:
        return ()
    raw_events = stored.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("CareEvent history must contain an events list")
    events = tuple(_deserialize_event(item) for item in raw_events)
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("CareEvent history contains duplicate event ids")
    return _sort_events(events)


def _deserialize_event(raw_event: object) -> CareEvent:
    """Deserialize and validate one stored event."""
    if not isinstance(raw_event, Mapping):
        raise ValueError("stored event must be an object")
    raw = cast("Mapping[str, object]", raw_event)
    metadata = raw["metadata"]
    if not isinstance(metadata, Mapping):
        raise ValueError("event metadata must be an object")
    context = raw.get("context", {})
    if not isinstance(context, Mapping):
        raise ValueError("event context must be an object")
    environmental_snapshot = raw.get("environmental_snapshot", {})
    if not isinstance(environmental_snapshot, Mapping):
        raise ValueError("event environmental_snapshot must be an object")
    attachments = raw.get("attachment_references", [])
    if not isinstance(attachments, list):
        raise ValueError("event attachment_references must be an array")
    return CareEvent(
        event_id=UUID(str(raw["event_id"])),
        reptile_id=str(raw["reptile_id"]),
        timestamp=datetime.fromisoformat(str(raw["timestamp"])),
        event_type=CareEventType(str(raw["event_type"])),
        task_id=None if raw.get("task_id") is None else str(raw["task_id"]),
        care_plan_id=(
            None if raw.get("care_plan_id") is None else str(raw["care_plan_id"])
        ),
        outcome_id=None if raw.get("outcome_id") is None else str(raw["outcome_id"]),
        context=cast("Mapping[str, Any]", context),
        actor_id=None if raw.get("actor_id") is None else str(raw["actor_id"]),
        source=None if raw.get("source") is None else str(raw["source"]),
        environmental_snapshot=cast(
            "Mapping[str, Any]",
            environmental_snapshot,
        ),
        attachment_references=tuple(str(item) for item in attachments),
        metadata=cast("Mapping[str, Any]", metadata),
    )


def _json_value(value: Any) -> Any:
    """Convert immutable metadata containers back to JSON-compatible values."""
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_json_value(item) for item in value]
    return value


class MemoryCareEventStore:
    """In-memory CareEventStore implementation for tests."""

    def __init__(self, events: tuple[CareEvent, ...] = ()) -> None:
        """Initialize with a deterministic immutable event collection."""
        self._events = _sort_events(tuple(events))

    async def async_load(self) -> None:
        """Keep the in-memory events available without extra work."""

    async def async_append_event(self, event: CareEvent) -> None:
        """Append one unique event to the in-memory collection."""
        if any(existing.event_id == event.event_id for existing in self._events):
            raise ValueError(f"Duplicate event id: {event.event_id}")
        self._events = _sort_events((*self._events, event))

    async def async_get_event(self, event_id: UUID) -> CareEvent | None:
        """Return one event by identifier when present."""
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None

    async def async_list_events(
        self, *, reptile_id: str | None = None
    ) -> tuple[CareEvent, ...]:
        """Return the in-memory events in chronological order."""
        if reptile_id is None:
            return self._events
        return tuple(event for event in self._events if event.reptile_id == reptile_id)
