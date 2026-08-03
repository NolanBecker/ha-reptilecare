"""Tests for persistent CareTask storage."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.reptilecare.care_plan_storage import (
    HomeAssistantCarePlanPersistence,
)
from custom_components.reptilecare.care_task_storage import (
    HomeAssistantCareTaskPersistence,
    migrate_care_task_storage,
)
from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
)
from custom_components.reptilecare.domain.care_task import (
    CareTask,
    CareTaskRepository,
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
TASK_ID = "223e4567-e89b-12d3-a456-426614174000"


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
    )


def _task() -> CareTask:
    return CareTask(
        task_id=TASK_ID,
        reptile_id=PIXEL_ID,
        care_plan_id=PLAN_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        due_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
        created_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        generation_key="task|pixel|2026-08-03T12:00:00+00:00",
        generated_by="care_plan:123e4567-e89b-12d3-a456-426614174000:v1",
        workflow_chain_id="323e4567-e89b-12d3-a456-426614174000",
    )


async def _reptile_repository() -> ReptileRepository:
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    await repository.async_add(_pixel())
    return repository


async def _care_plan_repository(
    hass: HomeAssistant, entry_id: str
) -> CarePlanRepository:
    repository = CarePlanRepository(
        await _reptile_repository(),
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        HomeAssistantCarePlanPersistence(hass, entry_id),
    )
    await repository.async_load()
    if repository.all() == ():
        await repository.async_add(_plan())
    return repository


async def test_care_task_repository_persists_across_restarts(
    hass: HomeAssistant,
) -> None:
    """Persisted CareTasks survive repository reconstruction."""
    care_plan_repository = await _care_plan_repository(hass, "care-task-persistence")
    repository = CareTaskRepository(
        await _reptile_repository(),
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        HomeAssistantCareTaskPersistence(hass, "care-task-persistence"),
    )
    await repository.async_load()
    await repository.async_add(_task())

    restored = CareTaskRepository(
        await _reptile_repository(),
        await _care_plan_repository(hass, "care-task-persistence"),
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        HomeAssistantCareTaskPersistence(hass, "care-task-persistence"),
    )
    await restored.async_load()
    assert restored.get(TASK_ID) == _task()


async def test_corrupted_care_task_storage_recovers_empty(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed CareTask storage recovers without breaking integration setup."""
    persistence = HomeAssistantCareTaskPersistence(hass, "corrupt-care-tasks")
    persistence._store.async_load = AsyncMock(return_value={"care_tasks": "invalid"})

    assert await persistence.async_load() == ()
    assert "Unable to load ReptileCare care tasks" in caplog.text


def test_care_task_storage_migration() -> None:
    """CareTask storage has an explicit migration boundary."""
    legacy = {"care_tasks": [1, 2, 3]}
    assert migrate_care_task_storage(0, 0, legacy) == legacy
    assert migrate_care_task_storage(1, 0, legacy) == legacy
    assert migrate_care_task_storage(1, 1, legacy) is legacy
    assert migrate_care_task_storage(0, 0, {"care_tasks": "invalid"}) == {
        "care_tasks": []
    }
    with pytest.raises(ValueError, match="Unsupported"):
        migrate_care_task_storage(2, 0, legacy)
