"""Tests for persistent CarePlan storage."""

from datetime import date
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.reptilecare.care_plan_storage import (
    HomeAssistantCarePlanPersistence,
    migrate_care_plan_storage,
)
from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
    ReminderConfiguration,
)
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.domain.task_template import TaskTemplateRegistry
from custom_components.reptilecare.domain.workflow import WorkflowRegistry

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "123e4567-e89b-12d3-a456-426614174000"


def _pixel() -> Reptile:
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )


def _plan() -> CarePlan:
    return CarePlan(
        care_plan_id=PLAN_ID,
        reptile_id=PIXEL_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        display_name="Feed Pixel Fruit",
        schedule=IntervalSchedule(every=2, unit=CarePlanScheduleUnit.DAYS),
        effective_date=date(2026, 8, 3),
        reminder_configuration=ReminderConfiguration(),
    )


async def _reptile_repository() -> ReptileRepository:
    """Create a loaded reptile repository containing Pixel."""
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    await repository.async_add(_pixel())
    return repository


async def test_care_plan_repository_persists_across_restarts(
    hass: HomeAssistant,
) -> None:
    """Persisted CarePlans survive repository reconstruction."""
    reptile_repository = await _reptile_repository()

    repository = CarePlanRepository(
        reptile_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        HomeAssistantCarePlanPersistence(hass, "care-plan-persistence"),
    )
    await repository.async_load()
    await repository.async_add(_plan())

    restored = CarePlanRepository(
        await _reptile_repository(),
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        HomeAssistantCarePlanPersistence(hass, "care-plan-persistence"),
    )
    await restored.async_load()
    assert restored.get(PLAN_ID) == _plan()


async def test_corrupted_care_plan_storage_recovers_empty(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed CarePlan storage recovers without breaking integration setup."""
    persistence = HomeAssistantCarePlanPersistence(hass, "corrupt-care-plans")
    persistence._store.async_load = AsyncMock(return_value={"care_plans": "invalid"})

    assert await persistence.async_load() == ()
    assert "Unable to load ReptileCare care plans" in caplog.text


def test_care_plan_storage_migration() -> None:
    """CarePlan storage has an explicit migration boundary."""
    legacy = {"care_plans": [1, 2, 3]}
    assert migrate_care_plan_storage(0, 0, legacy) == legacy
    assert migrate_care_plan_storage(1, 0, legacy) == legacy
    assert migrate_care_plan_storage(1, 1, legacy) is legacy
    assert migrate_care_plan_storage(0, 0, {"care_plans": "invalid"}) == {
        "care_plans": []
    }
    with pytest.raises(ValueError, match="Unsupported"):
        migrate_care_plan_storage(2, 0, legacy)
