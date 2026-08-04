"""Tests for CareTask models, serialization, and repository behavior."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock

import pytest

from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
    MemoryCarePlanPersistence,
)
from custom_components.reptilecare.domain.care_task import (
    CareTask,
    CareTaskDueState,
    CareTaskNotFoundError,
    CareTaskRepository,
    CareTaskStatus,
    DuplicateCareTaskError,
    DuplicateGenerationKeyError,
    InvalidCareTaskError,
    MemoryCareTaskPersistence,
    UnknownCarePlanReferenceError,
    UnknownTaskReptileError,
    UnknownTaskTemplateReferenceError,
    UnknownWorkflowReferenceError,
    care_task_from_dict,
    care_task_to_dict,
    project_due_state,
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


@pytest.fixture
def pixel() -> Reptile:
    """Return the test reptile used by CareTask fixtures."""
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )


async def _reptile_repository(pixel: Reptile) -> ReptileRepository:
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    await repository.async_add(pixel)
    return repository


async def _repository(
    pixel: Reptile,
    persistence: MemoryCareTaskPersistence,
) -> CareTaskRepository:
    reptile_repository = await _reptile_repository(pixel)
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        MemoryCarePlanPersistence((_plan(),)),
    )
    await care_plan_repository.async_load()
    repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
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
        schedule=IntervalSchedule(every=2, unit=CarePlanScheduleUnit.DAYS),
        effective_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
    )


def _task(**changes: object) -> CareTask:
    task = CareTask(
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
        attachment_references=("photo-1",),
    )
    return replace(task, **changes)


def test_care_task_is_immutable_and_normalized() -> None:
    """CareTasks normalize values and remain immutable."""
    task = CareTask(
        task_id=TASK_ID,
        reptile_id=PIXEL_ID,
        care_plan_id=PLAN_ID,
        task_template_id=" builtin:feed_fruit ",
        workflow_id=" builtin:feeding_cycle ",
        due_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
        created_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        generation_key=" generation-key ",
        generated_by=" manual import ",
    )

    assert task.task_template_id == "builtin:feed_fruit"
    assert task.workflow_id == "builtin:feeding_cycle"
    assert task.generation_key == "generation-key"
    assert task.generated_by == "manual import"
    with pytest.raises(FrozenInstanceError):
        task.notes = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: replace(_task(), task_id="not-a-uuid"),
            "task_id",
        ),
        (
            lambda: replace(
                _task(),
                due_at=datetime(2026, 8, 3, 12, tzinfo=UTC).replace(tzinfo=None),
            ),
            "timezone-aware",
        ),
        (
            lambda: replace(
                _task(),
                status="bad",  # type: ignore[arg-type]
            ),
            "status",
        ),
        (
            lambda: replace(
                _task(),
                generation_reason="bad",  # type: ignore[arg-type]
            ),
            "generation_reason",
        ),
        (
            lambda: replace(
                _task(),
                status=CareTaskStatus.COMPLETED,
                completed_at=None,
            ),
            "completed_at is required",
        ),
        (
            lambda: replace(
                _task(),
                completed_at=datetime(2026, 8, 3, 13, tzinfo=UTC),
            ),
            "must be unset",
        ),
        (
            lambda: replace(_task(), workflow_chain_id="not-a-uuid"),
            "workflow_chain_id",
        ),
    ],
)
def test_care_task_rejects_invalid_values(factory: object, message: str) -> None:
    """CareTask fields reject malformed values."""
    with pytest.raises(InvalidCareTaskError, match=message):
        factory()  # type: ignore[operator]


def test_care_task_serialization_round_trip() -> None:
    """CareTasks round-trip through explicit JSON-compatible serialization."""
    task = _task()
    serialized = care_task_to_dict(task)
    restored = care_task_from_dict(json.loads(json.dumps(serialized)))
    assert restored == task
    assert serialized["attachment_references"] == ["photo-1"]
    assert serialized["generation_reason"] == "recurring_care_plan"


def test_care_task_deserialization_rejects_invalid_documents() -> None:
    """Serialized CareTasks reject unsupported schema and malformed values."""
    serialized = care_task_to_dict(_task())
    serialized["unknown"] = True
    with pytest.raises(InvalidCareTaskError, match="unknown keys"):
        care_task_from_dict(serialized)

    serialized = care_task_to_dict(_task())
    serialized["schema_version"] = 3
    with pytest.raises(InvalidCareTaskError, match="unsupported schema"):
        care_task_from_dict(serialized)

    serialized = care_task_to_dict(_task())
    serialized.pop("workflow_node_id")
    serialized.pop("resolution_action")
    serialized.pop("resolution_actor_id")
    serialized.pop("resolution_source")
    serialized.pop("environmental_context")
    serialized.pop("resolution_key")
    serialized.pop("resolution_reconciled_at")
    serialized["schema_version"] = 1
    restored = care_task_from_dict(serialized)
    assert restored.task_id == TASK_ID

    serialized = care_task_to_dict(_task())
    serialized["created_at"] = "not-a-datetime"
    with pytest.raises(InvalidCareTaskError, match="ISO datetime"):
        care_task_from_dict(serialized)


def test_due_state_projection_boundaries() -> None:
    """Due and overdue remain derived from time, status, and snoozing."""
    task = _task()
    assert (
        project_due_state(
            task,
            now=datetime(2026, 8, 3, 11, 59, tzinfo=UTC),
        )
        is CareTaskDueState.UPCOMING
    )
    assert (
        project_due_state(
            task,
            now=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        )
        is CareTaskDueState.DUE
    )
    assert (
        project_due_state(
            task,
            now=datetime(2026, 8, 3, 12, 5, tzinfo=UTC),
            overdue_grace=timedelta(minutes=10),
        )
        is CareTaskDueState.DUE
    )
    assert (
        project_due_state(
            task,
            now=datetime(2026, 8, 3, 12, 11, tzinfo=UTC),
            overdue_grace=timedelta(minutes=10),
        )
        is CareTaskDueState.OVERDUE
    )
    assert (
        project_due_state(
            replace(
                task,
                snoozed_until=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            ),
            now=datetime(2026, 8, 3, 12, 15, tzinfo=UTC),
        )
        is CareTaskDueState.SNOOZED
    )
    assert (
        project_due_state(
            replace(
                task,
                status=CareTaskStatus.COMPLETED,
                completed_at=datetime(2026, 8, 3, 12, 1, tzinfo=UTC),
            ),
            now=datetime(2026, 8, 3, 13, 0, tzinfo=UTC),
        )
        is CareTaskDueState.TERMINAL
    )


async def test_repository_crud_and_lookup(pixel: Reptile) -> None:
    """Repository add, lookup, list, update, remove, and filters persist."""
    persistence = MemoryCareTaskPersistence()
    repository = await _repository(pixel, persistence)
    task = _task()
    await repository.async_add(task)

    assert repository.get(TASK_ID) == task
    assert repository.get_by_generation_key(task.generation_key) == task
    assert repository.contains_generation_key(task.generation_key)
    assert repository.all() == (task,)
    assert repository.for_reptile(PIXEL_ID) == (task,)
    assert repository.for_care_plan(PLAN_ID) == (task,)
    assert repository.pending() == (task,)
    assert repository.due_between(
        datetime(2026, 8, 3, 11, tzinfo=UTC),
        datetime(2026, 8, 3, 13, tzinfo=UTC),
    ) == (task,)

    updated = replace(task, notes="Offer mango")
    await repository.async_update(updated)
    assert repository.get(TASK_ID).notes == "Offer mango"

    await repository.async_disable(TASK_ID)
    disabled = repository.get(TASK_ID)
    assert disabled.status is CareTaskStatus.CANCELLED
    await repository.async_enable(TASK_ID)
    assert repository.get(TASK_ID).status is CareTaskStatus.PENDING
    assert repository.get(TASK_ID).completed_at is None

    removed = await repository.async_remove(TASK_ID)
    assert removed.task_id == TASK_ID
    assert repository.all() == ()
    assert persistence.tasks == ()


async def test_repository_rejects_duplicates(pixel: Reptile) -> None:
    """Task identity and generation keys remain unique."""
    repository = await _repository(pixel, MemoryCareTaskPersistence())
    task = _task()
    await repository.async_add(task)

    with pytest.raises(DuplicateCareTaskError, match=TASK_ID):
        await repository.async_add(task)
    with pytest.raises(DuplicateGenerationKeyError, match="generation_key"):
        await repository.async_add(
            replace(
                task,
                task_id="423e4567-e89b-12d3-a456-426614174000",
            )
        )


async def test_repository_rejects_invalid_references(pixel: Reptile) -> None:
    """Each task must reference known reptile, plan, template, and workflow data."""
    repository = await _repository(pixel, MemoryCareTaskPersistence())
    with pytest.raises(UnknownTaskReptileError, match="unknown reptile"):
        await repository.async_add(
            replace(
                _task(),
                task_id="423e4567-e89b-12d3-a456-426614174000",
                reptile_id="523e4567-e89b-12d3-a456-426614174000",
            )
        )
    with pytest.raises(UnknownCarePlanReferenceError, match="unknown care plan"):
        await repository.async_add(
            replace(
                _task(),
                task_id="623e4567-e89b-12d3-a456-426614174000",
                care_plan_id="723e4567-e89b-12d3-a456-426614174000",
            )
        )
    with pytest.raises(
        UnknownTaskTemplateReferenceError,
        match="unknown task template",
    ):
        await repository.async_add(
            replace(
                _task(),
                task_id="823e4567-e89b-12d3-a456-426614174000",
                task_template_id="builtin:missing_template",
            )
        )
    with pytest.raises(UnknownWorkflowReferenceError, match="unknown workflow"):
        await repository.async_add(
            replace(
                _task(),
                task_id="923e4567-e89b-12d3-a456-426614174000",
                workflow_id="builtin:missing_workflow",
            )
        )


async def test_repository_lookup_failures(pixel: Reptile) -> None:
    """Missing lookup and remove operations fail explicitly."""
    repository = await _repository(pixel, MemoryCareTaskPersistence())
    with pytest.raises(CareTaskNotFoundError, match="missing"):
        repository.get("missing")
    with pytest.raises(CareTaskNotFoundError, match="missing"):
        repository.get_by_generation_key("missing")
    with pytest.raises(CareTaskNotFoundError, match="missing"):
        await repository.async_remove("missing")


async def test_repository_validates_loaded_collection(pixel: Reptile) -> None:
    """Duplicate or invalid persisted tasks never enter runtime state."""
    reptile_repository = await _reptile_repository(pixel)
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        MemoryCarePlanPersistence((_plan(),)),
    )
    await care_plan_repository.async_load()
    repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        MemoryCareTaskPersistence((_task(), _task())),
    )
    with pytest.raises(DuplicateCareTaskError, match=TASK_ID):
        await repository.async_load()


async def test_failed_save_does_not_publish_task(pixel: Reptile) -> None:
    """Repository state remains durable when persistence rejects a mutation."""
    persistence = MemoryCareTaskPersistence()
    repository = await _repository(pixel, persistence)
    persistence.async_save = AsyncMock(side_effect=OSError("disk unavailable"))
    with pytest.raises(OSError, match="disk unavailable"):
        await repository.async_add(_task())
    assert repository.all() == ()
