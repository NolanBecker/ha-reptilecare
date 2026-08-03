"""Tests for CarePlan models, serialization, and repository behavior."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
import json
from unittest.mock import AsyncMock

import pytest

from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanNotFoundError,
    CarePlanRepository,
    CarePlanScheduleType,
    CarePlanScheduleUnit,
    DuplicateCarePlanError,
    IntervalSchedule,
    InvalidCarePlanError,
    MemoryCarePlanPersistence,
    ReminderConfiguration,
    ReminderLeadTime,
    ReminderLeadTimeUnit,
    ReminderRepeatPolicy,
    UnknownReptileError,
    UnknownTaskTemplateError,
    UnknownWorkflowGraphError,
    care_plan_from_dict,
    care_plan_to_dict,
)
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.domain.task_template import (
    TaskPriority,
    TaskTemplateRegistry,
)
from custom_components.reptilecare.domain.workflow import WorkflowRegistry

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "123e4567-e89b-12d3-a456-426614174000"


@pytest.fixture
def pixel() -> Reptile:
    """Return the test-only reptile used by CarePlan fixtures."""
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )


async def _reptile_repository(pixel: Reptile) -> ReptileRepository:
    """Return a loaded reptile repository containing Pixel."""
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    await repository.async_add(pixel)
    return repository


@pytest.fixture
def persistence() -> MemoryCarePlanPersistence:
    """Return empty Home Assistant-independent CarePlan persistence."""
    return MemoryCarePlanPersistence()


async def _repository(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> CarePlanRepository:
    """Return a loaded CarePlan repository with built-in registries."""
    reptile_repository = await _reptile_repository(pixel)
    repository = CarePlanRepository(
        reptile_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        persistence,
    )
    await repository.async_load()
    return repository


def _plan() -> CarePlan:
    return CarePlan(
        care_plan_id=PLAN_ID,
        reptile_id=PIXEL_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        display_name="Feed Pixel Fruit",
        enabled=True,
        priority=TaskPriority.NORMAL,
        schedule=IntervalSchedule(
            schedule_type=CarePlanScheduleType.INTERVAL,
            every=2,
            unit=CarePlanScheduleUnit.DAYS,
        ),
        effective_date=date(2026, 8, 3),
        reminder_configuration=ReminderConfiguration(
            enabled=True,
            lead_time=ReminderLeadTime(amount=6, unit=ReminderLeadTimeUnit.HOURS),
            repeat_policy=ReminderRepeatPolicy.REPEAT_UNTIL_DUE,
            metadata={"channel": "future"},
        ),
        metadata={"origin": "fixture"},
    )


def test_care_plan_is_immutable_and_normalized() -> None:
    """CarePlans normalize values and remain immutable."""
    schedule = IntervalSchedule(every=2, unit=CarePlanScheduleUnit.DAYS)
    plan = CarePlan(
        care_plan_id=PLAN_ID,
        reptile_id=PIXEL_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        display_name=" Feed Pixel Fruit ",
        schedule=schedule,
        effective_date=date(2026, 8, 3),
    )

    assert plan.display_name == "Feed Pixel Fruit"
    assert plan.priority is TaskPriority.NORMAL
    with pytest.raises(FrozenInstanceError):
        plan.display_name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: IntervalSchedule(every=0, unit=CarePlanScheduleUnit.DAYS),
            "schedule interval",
        ),
        (
            lambda: IntervalSchedule(
                every=1,
                unit=CarePlanScheduleUnit.DAYS,
                schedule_type="fixed",  # type: ignore[arg-type]
            ),
            "schedule_type",
        ),
        (
            lambda: ReminderLeadTime(amount=0, unit=ReminderLeadTimeUnit.HOURS),
            "lead_time amount",
        ),
        (
            lambda: ReminderConfiguration(enabled=True),
            "lead_time is required",
        ),
        (
            lambda: ReminderConfiguration(
                enabled=False,
                lead_time=ReminderLeadTime(1, ReminderLeadTimeUnit.DAYS),
                repeat_policy="bad",  # type: ignore[arg-type]
            ),
            "repeat_policy",
        ),
        (
            lambda: replace(_plan(), care_plan_id="not-a-uuid"),
            "care_plan_id",
        ),
        (
            lambda: replace(_plan(), reptile_id="not-a-uuid"),
            "reptile_id",
        ),
        (
            lambda: replace(_plan(), task_template_id="feed_fruit"),
            "task_template_id",
        ),
        (
            lambda: replace(_plan(), workflow_id="feeding_cycle"),
            "workflow_id",
        ),
        (
            lambda: replace(_plan(), priority="bad"),  # type: ignore[arg-type]
            "priority",
        ),
        (
            lambda: replace(_plan(), optional_end_date=date(2026, 8, 2)),
            "optional_end_date",
        ),
        (
            lambda: replace(_plan(), metadata=[]),  # type: ignore[arg-type]
            "metadata",
        ),
    ],
)
def test_care_plan_rejects_invalid_values(factory: object, message: str) -> None:
    """CarePlan fields and nested value objects reject malformed values."""
    with pytest.raises(InvalidCarePlanError, match=message):
        factory()  # type: ignore[operator]


def test_care_plan_serialization_round_trip() -> None:
    """CarePlans round-trip through explicit JSON-compatible serialization."""
    plan = _plan()
    serialized = care_plan_to_dict(plan)
    restored = care_plan_from_dict(json.loads(json.dumps(serialized)))
    assert restored == plan
    assert serialized["schedule"]["every"] == 2
    assert serialized["reminder_configuration"]["lead_time"] == {
        "amount": 6,
        "unit": "hours",
    }


def test_care_plan_deserialization_rejects_invalid_documents() -> None:
    """Serialized CarePlans reject unsupported schema and malformed values."""
    serialized = care_plan_to_dict(_plan())
    serialized["unknown"] = True
    with pytest.raises(InvalidCarePlanError, match="unknown keys"):
        care_plan_from_dict(serialized)

    serialized = care_plan_to_dict(_plan())
    serialized["schema_version"] = 2
    with pytest.raises(InvalidCarePlanError, match="unsupported schema"):
        care_plan_from_dict(serialized)

    serialized = care_plan_to_dict(_plan())
    serialized["effective_date"] = "not-a-date"
    with pytest.raises(InvalidCarePlanError, match="ISO date"):
        care_plan_from_dict(serialized)

    with pytest.raises(InvalidCarePlanError, match="care plan must be an object"):
        care_plan_from_dict([])  # type: ignore[arg-type]


async def test_repository_crud(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> None:
    """Repository add, lookup, list, update, and remove persist atomically."""
    repository = await _repository(pixel, persistence)
    plan = _plan()
    await repository.async_add(plan)
    assert repository.get(PLAN_ID) == plan
    assert repository.all() == (plan,)
    assert repository.for_reptile(PIXEL_ID) == (plan,)
    assert repository.for_template("builtin:feed_fruit") == (plan,)
    assert repository.for_enabled(True) == (plan,)
    assert persistence.care_plans == (plan,)

    renamed = replace(plan, display_name="Updated Display Name")
    await repository.async_update(renamed)
    assert repository.get(PLAN_ID) == renamed

    removed = await repository.async_remove(PLAN_ID)
    assert removed == renamed
    assert repository.all() == ()
    assert persistence.care_plans == ()


async def test_repository_enable_disable_and_filtering(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> None:
    """Disabled CarePlans remain stored but can be filtered out."""
    repository = await _repository(pixel, persistence)
    plan = _plan()
    await repository.async_add(plan)
    await repository.async_disable(PLAN_ID)
    assert not repository.get(PLAN_ID).enabled
    assert repository.all(include_disabled=False) == ()
    assert repository.for_enabled(False) == (repository.get(PLAN_ID),)
    await repository.async_enable(PLAN_ID)
    assert repository.get(PLAN_ID).enabled


async def test_repository_rejects_duplicate_ids(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> None:
    """CarePlan identifiers remain unique."""
    repository = await _repository(pixel, persistence)
    plan = _plan()
    await repository.async_add(plan)
    with pytest.raises(DuplicateCarePlanError, match=PLAN_ID):
        await repository.async_add(plan)


async def test_repository_rejects_invalid_references(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> None:
    """Every CarePlan must reference a known reptile, template, and workflow."""
    repository = await _repository(pixel, persistence)
    with pytest.raises(UnknownReptileError, match="unknown reptile"):
        await repository.async_add(
            replace(
                _plan(),
                care_plan_id="223e4567-e89b-12d3-a456-426614174000",
                reptile_id="323e4567-e89b-12d3-a456-426614174000",
            )
        )

    with pytest.raises(UnknownTaskTemplateError, match="unknown task template"):
        await repository.async_add(
            replace(
                _plan(),
                care_plan_id="423e4567-e89b-12d3-a456-426614174000",
                task_template_id="builtin:missing_template",
            )
        )

    with pytest.raises(UnknownWorkflowGraphError, match="unknown workflow graph"):
        await repository.async_add(
            replace(
                _plan(),
                care_plan_id="523e4567-e89b-12d3-a456-426614174000",
                workflow_id="builtin:missing_workflow",
            )
        )


async def test_repository_lookup_failures(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> None:
    """Missing lookup and removal operations fail explicitly."""
    repository = await _repository(pixel, persistence)
    with pytest.raises(CarePlanNotFoundError, match="missing"):
        repository.get("missing")
    with pytest.raises(CarePlanNotFoundError, match="missing"):
        await repository.async_remove("missing")


async def test_repository_validates_loaded_collection(
    pixel: Reptile,
) -> None:
    """Duplicate or invalid persisted records never enter runtime state."""
    plan = _plan()
    reptile_repository = await _reptile_repository(pixel)
    duplicate = CarePlanRepository(
        reptile_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        MemoryCarePlanPersistence((plan, plan)),
    )
    with pytest.raises(DuplicateCarePlanError, match=PLAN_ID):
        await duplicate.async_load()


async def test_failed_save_does_not_publish_care_plan(
    pixel: Reptile,
    persistence: MemoryCarePlanPersistence,
) -> None:
    """Repository state remains durable when persistence rejects a mutation."""
    repository = await _repository(pixel, persistence)
    persistence.async_save = AsyncMock(side_effect=OSError("disk unavailable"))
    with pytest.raises(OSError, match="disk unavailable"):
        await repository.async_add(_plan())
    assert repository.all() == ()
