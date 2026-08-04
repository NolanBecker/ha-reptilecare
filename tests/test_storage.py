"""Tests for persistent ReptileCare event storage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.storage import (
    HomeAssistantCareEventStore,
    MemoryCareEventStore,
    _deserialize_event,
    _deserialize_events,
    _json_value,
    migrate_storage,
)

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _event(hour: int, reptile_id: str = "pixel") -> CareEvent:
    """Create a deterministic persisted event."""
    return CareEvent(
        reptile_id=reptile_id,
        event_type=CareEventType.FEEDING,
        timestamp=BASE_TIME + timedelta(hours=hour),
        task_id="223e4567-e89b-12d3-a456-426614174000",
        care_plan_id="123e4567-e89b-12d3-a456-426614174000",
        outcome_id="ate_normally",
        context={"food_used": "papaya"},
        actor_id="keeper-1",
        source="service",
        environmental_snapshot={"temperature_f": 78},
        attachment_references=("photo-1",),
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
    assert await restored.async_get_event(earlier.event_id) == earlier
    assert restored._events[0].metadata["items"] == ("cricket",)
    assert restored._events[0].context["food_used"] == "papaya"
    assert restored._events[0].environmental_snapshot["temperature_f"] == 78


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
    assert migrate_storage(1, 0, legacy) == legacy
    with pytest.raises(ValueError, match="Unsupported"):
        migrate_storage(2, 0, legacy)


def test_deserialize_event_validates_payload_shapes() -> None:
    """Deserializer rejects malformed event object fields clearly."""
    with pytest.raises(ValueError, match="stored event must be an object"):
        _deserialize_event("bad")
    with pytest.raises(ValueError, match="event metadata must be an object"):
        _deserialize_event(
            {
                "event_id": str(_event(1).event_id),
                "reptile_id": "pixel",
                "timestamp": BASE_TIME.isoformat(),
                "event_type": "feeding",
                "metadata": [],
            }
        )
    with pytest.raises(
        ValueError, match="event attachment_references must be an array"
    ):
        _deserialize_event(
            {
                "event_id": str(_event(1).event_id),
                "reptile_id": "pixel",
                "timestamp": BASE_TIME.isoformat(),
                "event_type": "feeding",
                "metadata": {},
                "attachment_references": "bad",
            }
        )


def test_deserialize_events_rejects_duplicate_ids() -> None:
    """Stored collections must not contain duplicate event identifiers."""
    event = _event(1)
    payload = {
        "events": [
            {
                "event_id": str(event.event_id),
                "reptile_id": event.reptile_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "metadata": {},
            },
            {
                "event_id": str(event.event_id),
                "reptile_id": event.reptile_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "metadata": {},
            },
        ]
    }

    with pytest.raises(ValueError, match="duplicate event ids"):
        _deserialize_events(payload)


def test_storage_json_value_converts_immutable_containers() -> None:
    """Storage JSON conversion expands immutable containers back to JSON values."""
    assert _json_value({"items": ("cricket",), "flags": frozenset({1, 2})}) == {
        "items": ["cricket"],
        "flags": [1, 2],
    }


async def test_memory_store_filters_lists_and_detects_duplicates() -> None:
    """In-memory event storage mirrors the persisted store contract."""
    first = _event(1)
    second = _event(2, "echo")
    store = MemoryCareEventStore((first,))

    assert await store.async_get_event(first.event_id) == first
    assert await store.async_get_event(second.event_id) is None
    assert await store.async_list_events(reptile_id="pixel") == (first,)

    await store.async_append_event(second)
    assert await store.async_list_events() == (first, second)
    with pytest.raises(ValueError, match="Duplicate event id"):
        await store.async_append_event(first)
