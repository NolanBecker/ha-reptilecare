"""Tests for persistent Reptile storage."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.reptilecare.domain.reptile import (
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.reptile_storage import (
    HomeAssistantReptilePersistence,
    migrate_reptile_storage,
)
from custom_components.reptilecare.storage import HomeAssistantCareEventStore


def _pixel() -> Reptile:
    """Create the test-only sample reptile."""
    return Reptile("pixel", "Pixel", "builtin:gargoyle_gecko")


def _repository(hass: HomeAssistant, entry_id: str) -> ReptileRepository:
    """Create a persistent repository for one config entry."""
    return ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        HomeAssistantReptilePersistence(hass, entry_id),
    )


async def test_reptile_repository_persists_across_restarts(
    hass: HomeAssistant,
) -> None:
    """Persisted reptiles survive repository reconstruction."""
    repository = _repository(hass, "reptile-persistence")
    await repository.async_load()
    await repository.async_add(_pixel())

    restored = _repository(hass, "reptile-persistence")
    await restored.async_load()
    assert restored.get("pixel") == _pixel()


async def test_corrupted_reptile_storage_recovers_empty(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed reptile storage recovers without breaking integration setup."""
    persistence = HomeAssistantReptilePersistence(hass, "corrupt-reptiles")
    persistence._store.async_load = AsyncMock(return_value={"reptiles": "invalid"})

    assert await persistence.async_load() == ()
    assert "Unable to load ReptileCare reptiles" in caplog.text


def test_reptile_storage_migration() -> None:
    """Reptile storage has an explicit migration boundary."""
    legacy = {"reptiles": [{"reptile_id": "pixel"}]}
    assert migrate_reptile_storage(0, 0, legacy) == legacy
    assert migrate_reptile_storage(1, 0, legacy) is legacy
    assert migrate_reptile_storage(0, 0, {"reptiles": "invalid"}) == {"reptiles": []}
    with pytest.raises(ValueError, match="Unsupported"):
        migrate_reptile_storage(2, 0, legacy)


async def test_removing_reptile_preserves_care_events(hass: HomeAssistant) -> None:
    """Dedicated reptile storage cannot cascade into CareEvent history."""
    entry_id = "independent-storage"
    events = HomeAssistantCareEventStore(hass, entry_id)
    repository = _repository(hass, entry_id)
    await events.async_load()
    await repository.async_load()

    event = CareEvent(
        reptile_id="pixel",
        event_type=CareEventType.FEEDING,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await events.async_append_event(event)
    await repository.async_add(_pixel())
    await repository.async_remove("pixel")

    restored_events = HomeAssistantCareEventStore(hass, entry_id)
    await restored_events.async_load()
    assert await restored_events.async_list_events() == (event,)
