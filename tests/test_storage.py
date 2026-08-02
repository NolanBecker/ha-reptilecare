"""Tests for persistent ReptileCare event storage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.storage import (
    HomeAssistantCareEventStore,
    migrate_storage,
)

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _event(hour: int, reptile_id: str = "pixel") -> CareEvent:
    """Create a deterministic persisted event."""
    return CareEvent(
        reptile_id=reptile_id,
        event_type=CareEventType.FEEDING,
        timestamp=BASE_TIME + timedelta(hours=hour),
        metadata={"amount": 2, "items": ["cricket"]},
    )


async def test_store_saves_loads_orders_and_filters(hass: HomeAssistant) -> None:
    """Test that events survive reconstruction of the store."""
    store = HomeAssistantCareEventStore(hass, "persistent-entry")
    later = _event(2)
    earlier = _event(1)
    other = _event(3, "echo")

    await store.async_load()
    await store.async_append_event(later)
    await store.async_append_event(earlier)
    await store.async_append_event(other)

    restored = HomeAssistantCareEventStore(hass, "persistent-entry")
    await restored.async_load()

    assert await restored.async_list_events() == (earlier, later, other)
    assert await restored.async_list_events(reptile_id="pixel") == (earlier, later)
    assert restored._events[0].metadata["items"] == ("cricket",)


async def test_store_rejects_duplicate_event_id(hass: HomeAssistant) -> None:
    """Test that event identity remains unique in persisted history."""
    store = HomeAssistantCareEventStore(hass, "duplicate-entry")
    event = _event(1)
    await store.async_load()
    await store.async_append_event(event)

    with pytest.raises(ValueError, match="Duplicate event id"):
        await store.async_append_event(event)


async def test_failed_save_does_not_publish_event(hass: HomeAssistant) -> None:
    """Test in-memory history remains consistent when persistence fails."""
    store = HomeAssistantCareEventStore(hass, "failed-save-entry")
    await store.async_load()
    store._store.async_save = AsyncMock(side_effect=OSError("disk unavailable"))

    with pytest.raises(OSError, match="disk unavailable"):
        await store.async_append_event(_event(1))

    assert await store.async_list_events() == ()


async def test_corrupted_storage_recovers_empty(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test malformed stored data recovers as an empty history."""
    store = HomeAssistantCareEventStore(hass, "corrupt-entry")
    store._store.async_load = AsyncMock(return_value={"events": "not-a-list"})

    await store.async_load()

    assert await store.async_list_events() == ()
    assert "Unable to load ReptileCare CareEvent history" in caplog.text


def test_storage_migration() -> None:
    """Test migration of the initial pre-versioned event collection."""
    legacy = {"events": [{"event_id": "example"}]}

    assert migrate_storage(0, 0, legacy) == legacy
    assert migrate_storage(1, 0, legacy) is legacy
    with pytest.raises(ValueError, match="Unsupported"):
        migrate_storage(2, 0, legacy)
