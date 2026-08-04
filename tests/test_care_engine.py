"""Pure-Python tests for the CareEngine execution loop."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from custom_components.reptilecare.application import (
    CareEngine,
    CareTaskResolutionRequest,
    ConflictingTaskResolutionError,
    InvalidTaskContextError,
    InvalidTaskOutcomeSelectionError,
    ResolutionAction,
    WorkflowEvaluator,
)
from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
    MemoryCarePlanPersistence,
)
from custom_components.reptilecare.domain.care_task import (
    CareTask,
    CareTaskGenerationReason,
    CareTaskRepository,
    CareTaskStatus,
    MemoryCareTaskPersistence,
)
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.domain.task_outcome import TaskOutcome
from custom_components.reptilecare.domain.task_template import TaskTemplateRegistry
from custom_components.reptilecare.domain.workflow import WorkflowRegistry
from custom_components.reptilecare.storage import MemoryCareEventStore

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
        display_name="Feed Fruit",
        schedule=IntervalSchedule(every=2, unit=CarePlanScheduleUnit.DAYS),
        effective_date=date(2026, 8, 3),
    )


def _feed_task() -> CareTask:
    return CareTask(
        task_id=TASK_ID,
        reptile_id=PIXEL_ID,
        care_plan_id=PLAN_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        due_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
        created_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        generation_key="feed|pixel|2026-08-03T12:00:00+00:00",
        generated_by="care_plan:123e4567-e89b-12d3-a456-426614174000:v1",
        workflow_chain_id="323e4567-e89b-12d3-a456-426614174000",
        workflow_node_id="start",
    )


async def _build_engine(
    *tasks: CareTask,
) -> tuple[CareEngine, CareTaskRepository, MemoryCareEventStore]:
    reptile_repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await reptile_repository.async_load()
    await reptile_repository.async_add(_pixel())
    task_templates = TaskTemplateRegistry.load_builtin_templates()
    workflow_graphs = WorkflowRegistry.load_builtin_workflows()
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflow_graphs,
        MemoryCarePlanPersistence((_plan(),)),
    )
    await care_plan_repository.async_load()
    task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflow_graphs,
        MemoryCareTaskPersistence(tasks),
    )
    await task_repository.async_load()
    event_store = MemoryCareEventStore()
    engine = CareEngine(
        task_repository,
        task_templates,
        workflow_graphs,
        event_store,
        WorkflowEvaluator(workflow_graphs),
    )
    return engine, task_repository, event_store


def test_complete_feed_task_creates_event_and_follow_up() -> None:
    """Completing Feed Fruit creates one feeding event and Remove Food follow-up."""

    async def _run() -> None:
        engine, task_repository, event_store = await _build_engine(_feed_task())
        result = await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="ate_normally",
                outcome_metadata={"food_used": "papaya", "quantity": 30},
                notes="Ate normally",
                source="test",
                actor_id="keeper-1",
                completed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
                environmental_context={"temperature_f": 78},
            ),
        )

        assert result.task.status is CareTaskStatus.COMPLETED
        assert result.care_event.event_type.value == "feeding"
        assert result.care_event.task_id == TASK_ID
        assert result.care_event.outcome_id == "ate_normally"
        assert result.care_event.actor_id == "keeper-1"
        assert result.care_event.source == "test"
        assert result.care_event.environmental_snapshot["temperature_f"] == 78
        assert len(result.created_follow_up_tasks) == 1
        follow_up = result.created_follow_up_tasks[0]
        assert follow_up.task_template_id == "builtin:remove_food"
        assert follow_up.generation_reason is CareTaskGenerationReason.FOLLOW_UP
        assert follow_up.workflow_node_id == "create_remove_food_task"
        assert follow_up.parent_task_id == TASK_ID
        assert follow_up.due_at == datetime(2026, 8, 4, 12, 30, tzinfo=UTC)
        assert len(await event_store.async_list_events()) == 1
        assert len(task_repository.all()) == 2

    asyncio.run(_run())


def test_same_request_replays_without_duplicate_event_or_task() -> None:
    """Reapplying the same resolution reuses the first result."""

    async def _run() -> None:
        engine, _, event_store = await _build_engine(_feed_task())
        request = CareTaskResolutionRequest(
            action=ResolutionAction.COMPLETE,
            outcome_id="ate_partially",
            completed_at=datetime(2026, 8, 3, 12, 45, tzinfo=UTC),
        )
        first = await engine.async_resolve_task(TASK_ID, request)
        second = await engine.async_resolve_task(TASK_ID, request)

        assert not first.replayed_existing_result
        assert second.replayed_existing_result
        assert first.care_event.event_id == second.care_event.event_id
        assert len(first.created_follow_up_tasks) == 1
        assert second.created_follow_up_tasks == ()
        assert len(second.existing_follow_up_tasks) == 1
        assert len(await event_store.async_list_events()) == 1

    asyncio.run(_run())


def test_conflicting_second_resolution_fails() -> None:
    """A conflicting second terminal resolution is rejected clearly."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="ate_normally",
                completed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            ),
        )
        with pytest.raises(ConflictingTaskResolutionError, match=TASK_ID):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(
                    action=ResolutionAction.SKIP,
                    completed_at=datetime(2026, 8, 3, 12, 31, tzinfo=UTC),
                ),
            )

    asyncio.run(_run())


def test_invalid_outcome_and_context_fail_clearly() -> None:
    """Unknown outcomes and bad context fields are rejected before persistence."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        with pytest.raises(InvalidTaskOutcomeSelectionError, match="does not allow"):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="unknown_outcome",
                ),
            )
        with pytest.raises(InvalidTaskContextError, match="unknown context fields"):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="ate_normally",
                    outcome_metadata={"unknown_field": "value"},
                ),
            )

    asyncio.run(_run())


def test_skip_path_creates_event_without_follow_up() -> None:
    """Skipping Feed Fruit creates one event and follows the graph end path only."""

    async def _run() -> None:
        engine, task_repository, event_store = await _build_engine(_feed_task())
        result = await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.SKIP,
                completed_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
            ),
        )

        assert result.task.status is CareTaskStatus.SKIPPED
        assert result.care_event.event_type.value == "feeding"
        assert result.created_follow_up_tasks == ()
        assert result.existing_follow_up_tasks == ()
        assert result.workflow_completed
        assert len(task_repository.all()) == 1
        assert len(await event_store.async_list_events()) == 1

    asyncio.run(_run())


def test_remove_food_resolution_creates_next_feeding_task() -> None:
    """Completing Remove Food creates a food_removed event and next feed task."""

    async def _run() -> None:
        remove_food = CareTask(
            task_id="423e4567-e89b-12d3-a456-426614174000",
            reptile_id=PIXEL_ID,
            care_plan_id=PLAN_ID,
            task_template_id="builtin:remove_food",
            workflow_id="builtin:feeding_cycle",
            due_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
            created_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            generation_key="remove|pixel|2026-08-04T12:00:00+00:00",
            generated_by="care_engine:feed:create_remove_food_task",
            parent_task_id=TASK_ID,
            workflow_chain_id="323e4567-e89b-12d3-a456-426614174000",
            workflow_node_id="create_remove_food_task",
            generation_reason=CareTaskGenerationReason.FOLLOW_UP,
        )
        engine, task_repository, _ = await _build_engine(remove_food)
        result = await engine.async_resolve_task(
            remove_food.task_id,
            CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="completed",
                completed_at=datetime(2026, 8, 4, 12, 5, tzinfo=UTC),
            ),
        )

        assert result.care_event.event_type.value == "food_removed"
        assert len(result.created_follow_up_tasks) == 1
        next_feed = result.created_follow_up_tasks[0]
        assert next_feed.task_template_id == "builtin:feed_fruit"
        assert next_feed.workflow_node_id == "start"
        assert next_feed.parent_task_id == remove_food.task_id
        assert next_feed.generation_reason is CareTaskGenerationReason.FOLLOW_UP
        assert len(task_repository.all()) == 2

    asyncio.run(_run())


def test_reconcile_pending_operation_finishes_missing_follow_up() -> None:
    """Startup reconciliation resumes an interrupted terminal resolution safely."""

    async def _run() -> None:
        feed_task = replace(
            _feed_task(),
            status=CareTaskStatus.COMPLETED,
            completed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            outcome=TaskOutcome(outcome_id="ate_normally"),
            resolution_action="complete",
            resolution_source="test",
            resolution_key="reconcile-key",
        )
        engine, task_repository, event_store = await _build_engine(feed_task)
        reconciled = await engine.async_reconcile_pending_operations()

        assert reconciled == (TASK_ID,)
        updated = task_repository.get(TASK_ID)
        assert updated.resolution_reconciled_at is not None
        assert len(await event_store.async_list_events()) == 1
        assert len(task_repository.all()) == 2

    asyncio.run(_run())
