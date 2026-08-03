"""Tests for schedule calculation and CareTask generation."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
    MemoryCarePlanPersistence,
)
from custom_components.reptilecare.domain.care_task import (
    CareTaskGenerationReason,
    CareTaskRepository,
    MemoryCareTaskPersistence,
)
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.domain.task_template import TaskTemplateRegistry
from custom_components.reptilecare.domain.workflow import WorkflowRegistry
from custom_components.reptilecare.task_generation import (
    CareTaskGenerator,
    ScheduleCalculator,
)

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
BEANS_ID = "650e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "123e4567-e89b-12d3-a456-426614174000"
PLAN_ID_2 = "223e4567-e89b-12d3-a456-426614174000"


def _pixel(enabled: bool = True) -> Reptile:
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
        enabled=enabled,
    )


def _beans() -> Reptile:
    return Reptile(
        reptile_id=BEANS_ID,
        display_name="Beans",
        species_profile_id="builtin:gargoyle_gecko",
        slug="beans",
    )


def _plan(
    *,
    care_plan_id: str = PLAN_ID,
    reptile_id: str = PIXEL_ID,
    every: int = 2,
    unit: CarePlanScheduleUnit = CarePlanScheduleUnit.DAYS,
    effective_date: date = date(2026, 8, 3),
    optional_end_date: date | None = None,
    enabled: bool = True,
    task_template_id: str = "builtin:feed_fruit",
    workflow_id: str = "builtin:feeding_cycle",
    plan_version: int = 1,
) -> CarePlan:
    return CarePlan(
        care_plan_id=care_plan_id,
        reptile_id=reptile_id,
        task_template_id=task_template_id,
        workflow_id=workflow_id,
        display_name="Feed Fruit",
        enabled=enabled,
        schedule=IntervalSchedule(every=every, unit=unit),
        effective_date=effective_date,
        optional_end_date=optional_end_date,
        plan_version=plan_version,
    )


async def _reptile_repository(*reptiles: Reptile) -> ReptileRepository:
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    for reptile in reptiles:
        await repository.async_add(reptile)
    return repository


async def _care_plan_repository(
    reptile_repository: ReptileRepository, *plans: CarePlan
) -> CarePlanRepository:
    repository = CarePlanRepository(
        reptile_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        MemoryCarePlanPersistence(plans),
    )
    await repository.async_load()
    return repository


async def _task_repository(
    reptile_repository: ReptileRepository,
    care_plan_repository: CarePlanRepository,
    persistence: MemoryCareTaskPersistence | None = None,
) -> CareTaskRepository:
    repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        persistence or MemoryCareTaskPersistence(),
    )
    await repository.async_load()
    return repository


def test_schedule_first_and_next_occurrence_daily() -> None:
    """Daily schedules start at local midnight and advance by local days."""
    calculator = ScheduleCalculator(ZoneInfo("America/Chicago"))
    plan = _plan()

    first = calculator.first_occurrence(plan)
    second = calculator.next_occurrence(plan, first)

    assert first == datetime(2026, 8, 3, 5, tzinfo=UTC)
    assert second == datetime(2026, 8, 5, 5, tzinfo=UTC)


def test_schedule_supports_hourly_weekly_and_monthly() -> None:
    """Supported interval units preserve intended cadence."""
    calculator = ScheduleCalculator()
    hourly = _plan(unit=CarePlanScheduleUnit.HOURS, every=6)
    weekly = _plan(unit=CarePlanScheduleUnit.WEEKS, every=1)
    monthly = _plan(
        unit=CarePlanScheduleUnit.MONTHS,
        every=1,
        effective_date=date(2026, 1, 31),
    )

    first_hourly = calculator.first_occurrence(hourly)
    assert calculator.next_occurrence(hourly, first_hourly) == datetime(
        2026, 8, 3, 6, tzinfo=UTC
    )

    first_weekly = calculator.first_occurrence(weekly)
    assert calculator.next_occurrence(weekly, first_weekly) == datetime(
        2026, 8, 10, 0, tzinfo=UTC
    )

    first_monthly = calculator.first_occurrence(monthly)
    assert calculator.next_occurrence(monthly, first_monthly) == datetime(
        2026, 2, 28, 0, tzinfo=UTC
    )


def test_schedule_occurrences_respect_window_end_date_and_dst() -> None:
    """Occurrences remain bounded and honor local-time DST behavior."""
    calculator = ScheduleCalculator(ZoneInfo("America/Chicago"))
    plan = _plan(
        every=1,
        effective_date=date(2026, 3, 7),
        optional_end_date=date(2026, 3, 10),
    )

    occurrences = calculator.occurrences_between(
        plan,
        start=datetime(2026, 3, 7, 0, tzinfo=UTC),
        end=datetime(2026, 3, 12, 0, tzinfo=UTC),
    )

    assert occurrences == (
        datetime(2026, 3, 7, 6, tzinfo=UTC),
        datetime(2026, 3, 8, 6, tzinfo=UTC),
        datetime(2026, 3, 9, 5, tzinfo=UTC),
        datetime(2026, 3, 10, 5, tzinfo=UTC),
    )


async def test_task_generation_creates_and_reconciles_idempotently() -> None:
    """Repeated generation uses generation keys to avoid duplicates."""
    reptile_repository = await _reptile_repository(_pixel())
    care_plan_repository = await _care_plan_repository(reptile_repository, _plan())
    task_repository = await _task_repository(reptile_repository, care_plan_repository)
    generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        task_repository,
        ScheduleCalculator(),
    )

    first = await generator.async_generate(
        now=datetime(2026, 8, 3, 12, tzinfo=UTC),
        look_ahead=timedelta(days=3),
        look_back=timedelta(days=1),
    )
    second = await generator.async_generate(
        now=datetime(2026, 8, 3, 12, tzinfo=UTC),
        look_ahead=timedelta(days=3),
        look_back=timedelta(days=1),
    )

    assert len(first.created_task_ids) == 2
    assert second.created_task_ids == ()
    assert len(second.existing_task_ids) == 2
    assert len(task_repository.all()) == 2


async def test_task_generation_skips_disabled_and_expired_plans() -> None:
    """Disabled plans, expired plans, and disabled reptiles create no tasks."""
    reptile_repository = await _reptile_repository(_pixel(enabled=False))
    plans = (
        _plan(enabled=False),
        _plan(
            care_plan_id=PLAN_ID_2,
            effective_date=date(2026, 7, 30),
            optional_end_date=date(2026, 8, 1),
        ),
    )
    care_plan_repository = await _care_plan_repository(reptile_repository, *plans)
    task_repository = await _task_repository(reptile_repository, care_plan_repository)
    generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        task_repository,
        ScheduleCalculator(),
    )

    result = await generator.async_generate(
        now=datetime(2026, 8, 3, 12, tzinfo=UTC),
        look_ahead=timedelta(days=1),
        look_back=timedelta(days=0),
    )

    assert result.created_task_ids == ()
    assert result.skipped_plan_ids == (PLAN_ID, PLAN_ID_2)


async def test_task_generation_reports_broken_template_and_workflow() -> None:
    """Broken plan references are reported instead of silently ignored."""
    reptile_repository = await _reptile_repository(_pixel())
    care_plan_repository = await _care_plan_repository(
        reptile_repository,
        _plan(task_template_id="builtin:feed_fruit"),
    )
    task_repository = await _task_repository(reptile_repository, care_plan_repository)
    generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        task_repository,
        ScheduleCalculator(),
    )

    broken_template = replace(
        care_plan_repository.get(PLAN_ID),
        task_template_id="builtin:missing_template",
    )
    care_plan_repository._care_plans = {  # type: ignore[assignment]
        PLAN_ID: broken_template
    }
    result = await generator.async_generate(
        now=datetime(2026, 8, 3, 12, tzinfo=UTC),
        look_ahead=timedelta(days=1),
        look_back=timedelta(days=0),
    )
    assert "missing_template" in result.errors[PLAN_ID]

    broken_workflow = replace(
        broken_template,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:missing_workflow",
    )
    care_plan_repository._care_plans = {  # type: ignore[assignment]
        PLAN_ID: broken_workflow
    }
    result = await generator.async_generate(
        now=datetime(2026, 8, 3, 12, tzinfo=UTC),
        look_ahead=timedelta(days=1),
        look_back=timedelta(days=0),
    )
    assert "missing_workflow" in result.errors[PLAN_ID]


async def test_generation_horizon_and_multiple_reptiles_are_independent() -> None:
    """Generation windows stay bounded and shared templates do not collide."""
    reptile_repository = await _reptile_repository(_pixel(), _beans())
    care_plan_repository = await _care_plan_repository(
        reptile_repository,
        _plan(),
        _plan(care_plan_id=PLAN_ID_2, reptile_id=BEANS_ID),
    )
    task_repository = await _task_repository(reptile_repository, care_plan_repository)
    generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        task_repository,
        ScheduleCalculator(),
    )

    result = await generator.async_generate(
        now=datetime(2026, 8, 3, 1, tzinfo=UTC),
        look_ahead=timedelta(hours=1),
        look_back=timedelta(days=0),
    )
    assert result.created_task_ids == ()

    later = await generator.async_generate(
        now=datetime(2026, 8, 2, 12, tzinfo=UTC),
        look_ahead=timedelta(days=1),
        look_back=timedelta(days=0),
    )
    assert len(later.created_task_ids) == 2
    assert {task.reptile_id for task in task_repository.all()} == {PIXEL_ID, BEANS_ID}


async def test_restart_safe_reconciliation_recreates_only_missing_occurrence() -> None:
    """Missing logical tasks are recreated with stable deterministic keys."""
    reptile_repository = await _reptile_repository(_pixel())
    plan = _plan()
    care_plan_repository = await _care_plan_repository(reptile_repository, plan)
    persistence = MemoryCareTaskPersistence()
    task_repository = await _task_repository(
        reptile_repository,
        care_plan_repository,
        persistence,
    )
    generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        task_repository,
        ScheduleCalculator(),
    )
    now = datetime(2026, 8, 3, 12, tzinfo=UTC)

    original = await generator.async_generate(
        now=now,
        look_ahead=timedelta(days=3),
        look_back=timedelta(days=1),
    )
    tasks = task_repository.all()
    removed = await task_repository.async_remove(tasks[0].task_id)

    restored_repository = await _task_repository(
        reptile_repository,
        care_plan_repository,
        persistence,
    )
    restored_generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        TaskTemplateRegistry.load_builtin_templates(),
        WorkflowRegistry.load_builtin_workflows(),
        restored_repository,
        ScheduleCalculator(),
    )
    regenerated = await restored_generator.async_generate(
        now=now,
        look_ahead=timedelta(days=3),
        look_back=timedelta(days=1),
    )

    assert len(original.created_task_ids) == 2
    assert len(regenerated.created_task_ids) == 1
    recreated = restored_repository.get(regenerated.created_task_ids[0])
    assert recreated.generation_key == removed.generation_key
    assert recreated.generation_reason is CareTaskGenerationReason.SYSTEM_RECONCILIATION
