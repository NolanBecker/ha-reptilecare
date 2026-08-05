"""Pure-Python tests for ReptileCare entity projections."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
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
from custom_components.reptilecare.domain.task_template import (
    TaskPriority,
    TaskTemplateRegistry,
)
from custom_components.reptilecare.domain.workflow import WorkflowRegistry
from custom_components.reptilecare.entity_projection import ReptileCareEntityProjection
from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.timeline import Timeline

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "550e8400-e29b-41d4-a716-446655440001"
HIGH_PLAN_ID = "550e8400-e29b-41d4-a716-446655440002"
NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


async def _projection(
    *,
    reptiles: tuple[Reptile, ...],
    care_plans: tuple[CarePlan, ...],
    tasks: tuple[CareTask, ...] = (),
    events: tuple[CareEvent, ...] = (),
    now: datetime = NOW,
) -> ReptileCareEntityProjection:
    species_profiles = SpeciesProfileRegistry.load_builtin_profiles()
    task_templates = TaskTemplateRegistry.load_builtin_templates()
    workflows = WorkflowRegistry.load_builtin_workflows()

    reptile_repository = ReptileRepository(
        species_profiles,
        MemoryReptilePersistence(reptiles),
    )
    await reptile_repository.async_load()

    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflows,
        MemoryCarePlanPersistence(care_plans),
    )
    await care_plan_repository.async_load()

    task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflows,
        MemoryCareTaskPersistence(tasks),
    )
    await task_repository.async_load()

    return ReptileCareEntityProjection(
        reptile_repository,
        care_plan_repository,
        task_repository,
        task_templates,
        species_profiles,
        lambda: Timeline(events),
        now_provider=lambda: now,
    )


def _pixel(*, enabled: bool = True, slug: str = "pixel") -> Reptile:
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug=slug,
        enabled=enabled,
    )


def _plan(
    *,
    care_plan_id: str = PLAN_ID,
    task_template_id: str = "builtin:feed_fruit",
    display_name: str = "Feed Fruit",
    priority: TaskPriority = TaskPriority.NORMAL,
) -> CarePlan:
    return CarePlan(
        care_plan_id=care_plan_id,
        reptile_id=PIXEL_ID,
        task_template_id=task_template_id,
        workflow_id="builtin:feeding_cycle",
        display_name=display_name,
        priority=priority,
        schedule=IntervalSchedule(every=2, unit="days"),
        effective_date=date(2026, 8, 1),
    )


def _task(
    *,
    task_id: str,
    due_at: datetime,
    task_template_id: str = "builtin:feed_fruit",
    care_plan_id: str = PLAN_ID,
    status: CareTaskStatus = CareTaskStatus.PENDING,
    snoozed_until: datetime | None = None,
    completed_at: datetime | None = None,
    generation_reason: CareTaskGenerationReason = (
        CareTaskGenerationReason.RECURRING_CARE_PLAN
    ),
) -> CareTask:
    return CareTask(
        task_id=task_id,
        reptile_id=PIXEL_ID,
        care_plan_id=care_plan_id,
        task_template_id=task_template_id,
        workflow_id="builtin:feeding_cycle",
        due_at=due_at,
        created_at=NOW - timedelta(days=1),
        generation_key=f"gen-{task_id}",
        status=status,
        snoozed_until=snoozed_until,
        completed_at=completed_at,
        generation_reason=generation_reason,
    )


def test_projection_counts_next_task_and_latest_event() -> None:
    """Projection derives compact counts, next task, and latest event."""

    async def _run() -> None:
        events = (
            CareEvent(
                reptile_id=PIXEL_ID,
                event_type=CareEventType.FEEDING,
                timestamp=datetime(2026, 8, 4, 12, tzinfo=UTC),
            ),
            CareEvent(
                reptile_id=PIXEL_ID,
                event_type=CareEventType.HEALTH_NOTE,
                timestamp=datetime(2026, 8, 5, 9, tzinfo=UTC),
                source="home_assistant_service",
            ),
        )
        projection = await _projection(
            reptiles=(_pixel(),),
            care_plans=(_plan(priority=TaskPriority.HIGH),),
            tasks=(
                _task(task_id=str(uuid4()), due_at=NOW - timedelta(hours=1)),
                _task(task_id=str(uuid4()), due_at=NOW),
                _task(task_id=str(uuid4()), due_at=NOW + timedelta(hours=3)),
                _task(
                    task_id=str(uuid4()),
                    due_at=NOW - timedelta(hours=2),
                    snoozed_until=NOW + timedelta(hours=4),
                ),
                _task(
                    task_id=str(uuid4()),
                    due_at=NOW - timedelta(days=1),
                    status=CareTaskStatus.COMPLETED,
                    completed_at=NOW - timedelta(days=1),
                ),
            ),
            events=events,
        )

        reptile_projection = projection.project_reptile(PIXEL_ID)

        assert reptile_projection.pending_tasks.pending_count == 4
        assert reptile_projection.pending_tasks.overdue_count == 1
        assert reptile_projection.pending_tasks.due_count == 1
        assert reptile_projection.pending_tasks.upcoming_count == 1
        assert reptile_projection.pending_tasks.snoozed_count == 1
        assert len(reptile_projection.pending_tasks.task_ids) == 4
        assert reptile_projection.care_state == "overdue"
        assert reptile_projection.next_task is not None
        assert reptile_projection.next_task.display_name == "Feed Fruit Mix"
        assert reptile_projection.next_task.timing_state.value == "overdue"
        assert reptile_projection.last_event is not None
        assert reptile_projection.last_event.label == "Health Note"
        assert reptile_projection.last_event.source == "home_assistant_service"

    asyncio.run(_run())


def test_projection_uses_deterministic_tie_breaking_and_fallbacks() -> None:
    """Projection picks one next task deterministically and warns on bad refs."""

    async def _run() -> None:
        first_id = str(uuid4())
        second_id = str(uuid4())
        projection = await _projection(
            reptiles=(_pixel(),),
            care_plans=(
                _plan(priority=TaskPriority.LOW),
                _plan(
                    care_plan_id=HIGH_PLAN_ID,
                    display_name="High Priority Feed",
                    priority=TaskPriority.HIGH,
                ),
            ),
            tasks=(
                _task(task_id=second_id, due_at=NOW, care_plan_id=PLAN_ID),
                _task(
                    task_id=first_id,
                    due_at=NOW,
                    care_plan_id=HIGH_PLAN_ID,
                ),
            ),
        )
        original_get = projection._task_templates.get

        def _missing_template(template_id: str):
            if template_id == "builtin:feed_fruit":
                from custom_components.reptilecare.domain.task_template import (
                    TaskTemplateNotFoundError,
                )

                raise TaskTemplateNotFoundError(
                    "task template not found: builtin:feed_fruit"
                )
            return original_get(template_id)

        projection._task_templates.get = _missing_template

        reptile_projection = projection.project_reptile(PIXEL_ID)

        assert reptile_projection.next_task is not None
        assert reptile_projection.next_task.task_id == first_id
        assert reptile_projection.next_task.display_name == "High Priority Feed"
        assert reptile_projection.warnings == (
            f"missing task template for task {first_id}: builtin:feed_fruit",
        )

    asyncio.run(_run())


def test_projection_lists_disabled_reptiles_and_device_model() -> None:
    """Projection keeps disabled reptiles discoverable and resolves model text."""

    async def _run() -> None:
        projection = await _projection(
            reptiles=(_pixel(enabled=False),),
            care_plans=(),
        )

        assert projection.all_reptile_ids() == (PIXEL_ID,)
        assert projection.all_reptile_ids(include_disabled=False) == ()
        assert projection.species_model(PIXEL_ID) == "Gargoyle Gecko"

    asyncio.run(_run())
