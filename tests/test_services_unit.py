"""Pure-Python unit tests for ReptileCare service adapters."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.reptilecare.application import CareTaskResolutionResult
from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
    MemoryCarePlanPersistence,
)
from custom_components.reptilecare.domain.care_task import (
    CareTask,
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
from custom_components.reptilecare.domain.task_template import TaskTemplateRegistry
from custom_components.reptilecare.domain.workflow import WorkflowRegistry
from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.services import (
    _async_handle_create_care_plan,
    _async_handle_create_reptile,
    _async_handle_disable_care_plan,
    _async_handle_disable_reptile,
    _async_handle_enable_care_plan,
    _async_handle_enable_reptile,
    _async_handle_generate_tasks,
    _async_handle_get_tasks,
    _async_handle_get_timeline,
    _async_handle_log_event,
    _async_handle_preview_task_generation,
    _async_handle_resolve_task,
    _async_handle_system_health,
    _async_handle_update_care_plan,
    _async_handle_update_reptile,
)
from custom_components.reptilecare.storage import MemoryCareEventStore
from custom_components.reptilecare.task_generation import (
    TaskGenerationPreviewResult,
    TaskGenerationResult,
)

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "123e4567-e89b-12d3-a456-426614174000"
TASK_ID_1 = "223e4567-e89b-12d3-a456-426614174000"
TASK_ID_2 = "323e4567-e89b-12d3-a456-426614174000"
TASK_ID_3 = "423e4567-e89b-12d3-a456-426614174000"


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
        effective_date=date(2026, 8, 5),
    )


def _task(
    *,
    task_id: str,
    due_at: datetime,
    status: CareTaskStatus = CareTaskStatus.PENDING,
) -> CareTask:
    return CareTask(
        task_id=task_id,
        reptile_id=PIXEL_ID,
        care_plan_id=PLAN_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        due_at=due_at,
        created_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
        completed_at=(
            None
            if status is CareTaskStatus.PENDING
            else datetime(2026, 8, 5, 13, tzinfo=UTC)
        ),
        generation_key=f"task:{task_id}",
        status=status,
    )


async def _runtime_with_repositories(
    *,
    reptiles: tuple[Reptile, ...] = (),
    care_plans: tuple[CarePlan, ...] = (),
    tasks: tuple[CareTask, ...] = (),
    events: tuple[CareEvent, ...] = (),
) -> SimpleNamespace:
    species_profiles = SpeciesProfileRegistry.load_builtin_profiles()
    reptile_repository = ReptileRepository(
        species_profiles,
        MemoryReptilePersistence(reptiles),
    )
    await reptile_repository.async_load()
    task_templates = TaskTemplateRegistry.load_builtin_templates()
    workflow_graphs = WorkflowRegistry.load_builtin_workflows()
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflow_graphs,
        MemoryCarePlanPersistence(care_plans),
    )
    await care_plan_repository.async_load()
    care_task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflow_graphs,
        MemoryCareTaskPersistence(tasks),
    )
    await care_task_repository.async_load()

    event_store = MemoryCareEventStore(events)
    timeline = SimpleNamespace(all_events=lambda: events)
    coordinator = SimpleNamespace(
        async_refresh=lambda: asyncio.sleep(0),
        timeline=timeline,
    )

    return SimpleNamespace(
        coordinator=coordinator,
        event_store=event_store,
        species_profiles=species_profiles,
        reptile_repository=reptile_repository,
        task_templates=task_templates,
        workflow_graphs=workflow_graphs,
        care_plan_repository=care_plan_repository,
        care_task_repository=care_task_repository,
        care_task_generator=None,
        care_engine=None,
        timeline=timeline,
    )


def _call(
    data: dict[str, object],
    *,
    user_id: str | None = "keeper-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        hass=object(),
        context=SimpleNamespace(user_id=user_id),
    )


def test_reptile_and_care_plan_handlers(monkeypatch) -> None:
    """Service handlers persist reptile and care-plan changes through repositories."""

    async def _run() -> None:
        runtime = await _runtime_with_repositories()
        monkeypatch.setattr(
            "custom_components.reptilecare.services._runtime",
            lambda hass: runtime,
        )

        created = await _async_handle_create_reptile(
            _call(
                {
                    "display_name": "Pixel",
                    "slug": "pixel",
                    "species_profile_id": "builtin:gargoyle_gecko",
                }
            )
        )
        reptile = created["reptile"]
        assert reptile["display_name"] == "Pixel"
        assert reptile["slug"] == "pixel"

        updated = await _async_handle_update_reptile(
            _call(
                {
                    "reptile_id": reptile["reptile_id"],
                    "display_name": "Pixel Prime",
                    "notes": "Moved enclosures",
                    "slug": "pixel-prime",
                }
            )
        )
        assert updated["reptile"]["display_name"] == "Pixel Prime"
        assert updated["reptile"]["slug"] == "pixel-prime"

        disabled = await _async_handle_disable_reptile(_call({"slug": "pixel-prime"}))
        assert disabled["reptile"]["enabled"] is False

        enabled = await _async_handle_enable_reptile(
            _call({"reptile_id": reptile["reptile_id"]})
        )
        assert enabled["reptile"]["enabled"] is True

        created_plan = await _async_handle_create_care_plan(
            _call(
                {
                    "slug": "pixel-prime",
                    "task_template_id": "builtin:feed_fruit",
                    "workflow_id": "builtin:feeding_cycle",
                    "display_name": "Feed Fruit",
                    "schedule": {
                        "schedule_type": "interval",
                        "every": 2,
                        "unit": "days",
                    },
                    "metadata": {"channel": "manual"},
                }
            )
        )
        care_plan = created_plan["care_plan"]
        assert care_plan["task_template_id"] == "builtin:feed_fruit"
        assert care_plan["workflow_id"] == "builtin:feeding_cycle"

        updated_plan = await _async_handle_update_care_plan(
            _call(
                {
                    "care_plan_id": care_plan["care_plan_id"],
                    "display_name": "Feed Fruit Mix",
                    "enabled": False,
                    "schedule": {
                        "schedule_type": "interval",
                        "every": 3,
                        "unit": "days",
                    },
                }
            )
        )
        assert updated_plan["care_plan"]["display_name"] == "Feed Fruit Mix"
        assert updated_plan["care_plan"]["enabled"] is False

        enabled_plan = await _async_handle_enable_care_plan(
            _call({"care_plan_id": care_plan["care_plan_id"]})
        )
        assert enabled_plan["care_plan"]["enabled"] is True

        disabled_plan = await _async_handle_disable_care_plan(
            _call({"care_plan_id": care_plan["care_plan_id"]})
        )
        assert disabled_plan["care_plan"]["enabled"] is False

    asyncio.run(_run())


def test_generation_resolution_event_and_health_handlers(monkeypatch) -> None:
    """Task generation, resolution, event logging, and health responses are stable."""

    async def _run() -> None:
        now = datetime(2026, 8, 5, 12, tzinfo=UTC)
        runtime = await _runtime_with_repositories(
            reptiles=(_pixel(),),
            care_plans=(_plan(),),
            tasks=(_task(task_id=TASK_ID_2, due_at=now + timedelta(hours=2)),),
            events=(
                CareEvent(
                    reptile_id=PIXEL_ID,
                    event_type=CareEventType.HEALTH_NOTE,
                    timestamp=now,
                ),
            ),
        )
        preview_task = _task(task_id=TASK_ID_1, due_at=now + timedelta(days=1))
        resolved_task = _task(
            task_id=TASK_ID_3,
            due_at=now,
            status=CareTaskStatus.COMPLETED,
        )
        resolved_event = CareEvent(
            reptile_id=PIXEL_ID,
            event_type=CareEventType.FEEDING,
            timestamp=now,
            task_id=TASK_ID_3,
            care_plan_id=PLAN_ID,
            context={"quantity": 30},
            actor_id="keeper-1",
            source="home_assistant_service",
        )

        class FakeGenerator:
            async def async_generate(self, **kwargs) -> TaskGenerationResult:
                return TaskGenerationResult(
                    created_task_ids=(TASK_ID_1,),
                    existing_task_ids=(TASK_ID_2,),
                    skipped_plan_ids=("plan-skip",),
                    warnings=("generated warning",),
                    errors={"plan-error": "missing reptile"},
                )

            async def async_preview(self, **kwargs) -> TaskGenerationPreviewResult:
                return TaskGenerationPreviewResult(
                    would_create=(preview_task,),
                    already_exists=(preview_task,),
                    skipped_plan_ids=("plan-skip",),
                    warnings=("preview warning",),
                    errors={"plan-error": "already exists"},
                )

        class FakeEngine:
            async def async_resolve_task(
                self,
                task_id: str,
                request,
            ) -> CareTaskResolutionResult:
                assert task_id == TASK_ID_3
                assert request.actor_id == "keeper-1"
                return CareTaskResolutionResult(
                    task=resolved_task,
                    care_event=resolved_event,
                    created_follow_up_tasks=(preview_task,),
                    existing_follow_up_tasks=(),
                    workflow_completed=True,
                    replayed_existing_result=False,
                    warnings=("follow-up created",),
                )

        logged_events: list[CareEvent] = list(runtime.timeline.all_events())

        async def _append_event(event: CareEvent) -> None:
            logged_events.append(event)

        runtime.care_task_generator = FakeGenerator()
        runtime.care_engine = FakeEngine()
        runtime.event_store = SimpleNamespace(async_append_event=_append_event)
        runtime.timeline = SimpleNamespace(all_events=lambda: tuple(logged_events))
        runtime.coordinator = SimpleNamespace(
            async_refresh=lambda: asyncio.sleep(0),
            timeline=runtime.timeline,
        )

        monkeypatch.setattr(
            "custom_components.reptilecare.services._runtime",
            lambda hass: runtime,
        )

        generated = await _async_handle_generate_tasks(
            _call(
                {
                    "slug": "pixel",
                    "care_plan_id": PLAN_ID,
                    "now": now,
                    "horizon_duration": {"days": 1},
                }
            )
        )
        assert generated["created_task_ids"] == [TASK_ID_1]
        assert generated["existing_task_ids"] == [TASK_ID_2]
        assert generated["errors"] == {"plan-error": "missing reptile"}

        preview = await _async_handle_preview_task_generation(
            _call(
                {
                    "reptile_id": PIXEL_ID,
                    "care_plan_id": PLAN_ID,
                    "now": now,
                    "horizon_end": now + timedelta(days=2),
                }
            )
        )
        assert len(preview["would_create"]) == 1
        assert preview["already_exists"][0]["task_id"] == TASK_ID_1
        assert preview["warnings"] == [
            "preview warning",
            "care plan plan-error: already exists",
        ]

        resolved = await _async_handle_resolve_task(
            _call(
                {
                    "task_id": TASK_ID_3,
                    "action": "complete",
                    "outcome_id": "ate_normally",
                    "outcome_metadata": {"quantity": 30},
                    "notes": "Finished meal",
                    "environmental_context": {"temperature_f": 78},
                }
            )
        )
        assert resolved["task"]["status"] == "completed"
        assert resolved["care_event"]["context"]["quantity"] == 30
        assert resolved["created_follow_up_tasks"][0]["task_id"] == TASK_ID_1

        logged = await _async_handle_log_event(
            _call(
                {
                    "slug": "pixel",
                    "event_type": "health_note",
                    "timestamp": now,
                    "context": {"observation": "alert"},
                    "notes": "Looks good",
                    "environmental_context": {"humidity": 68},
                },
                user_id=None,
            )
        )
        assert logged["care_event"]["event_type"] == "health_note"
        assert logged["care_event"]["actor_id"] is None
        assert logged["care_event"]["metadata"]["notes"] == "Looks good"

        health = await _async_handle_system_health(_call({}))
        assert health["reptile_count"] == 1
        assert health["care_plan_count"] == 1
        assert health["pending_task_count"] == 1
        assert health["completed_task_count"] == 0
        assert health["care_event_count"] == 2

    asyncio.run(_run())


def test_query_handlers_filter_and_validate(monkeypatch) -> None:
    """Query handlers filter by identifiers, time windows, enums, and limits."""

    async def _run() -> None:
        now = datetime(2026, 8, 5, 12, tzinfo=UTC)
        runtime = await _runtime_with_repositories(
            reptiles=(_pixel(),),
            care_plans=(_plan(),),
            tasks=(
                _task(task_id=TASK_ID_1, due_at=now + timedelta(hours=3)),
                _task(task_id=TASK_ID_2, due_at=now - timedelta(hours=2)),
                _task(
                    task_id=TASK_ID_3,
                    due_at=now - timedelta(days=1),
                    status=CareTaskStatus.COMPLETED,
                ),
            ),
            events=(
                CareEvent(
                    reptile_id=PIXEL_ID,
                    event_type=CareEventType.FEEDING,
                    timestamp=now - timedelta(hours=2),
                ),
                CareEvent(
                    reptile_id=PIXEL_ID,
                    event_type=CareEventType.HEALTH_NOTE,
                    timestamp=now,
                ),
            ),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.services._runtime",
            lambda hass: runtime,
        )

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now if tz is not None else now.replace(tzinfo=None)

        monkeypatch.setattr(
            "custom_components.reptilecare.services.datetime",
            FixedDateTime,
        )

        tasks = await _async_handle_get_tasks(
            _call(
                {
                    "slug": "pixel",
                    "due_state": "upcoming",
                    "due_after": "2026-08-05T12:00:00+00:00",
                    "limit": 1,
                }
            )
        )
        assert [task["task_id"] for task in tasks["tasks"]] == [TASK_ID_1]

        completed = await _async_handle_get_tasks(
            _call(
                {
                    "slug": "pixel",
                    "status": "completed",
                    "include_terminal": True,
                    "due_before": "2026-08-05T12:00:00+00:00",
                }
            )
        )
        assert [task["task_id"] for task in completed["tasks"]] == [TASK_ID_3]

        timeline = await _async_handle_get_timeline(
            _call(
                {
                    "reptile_id": PIXEL_ID,
                    "event_type": "health_note",
                    "start": "2026-08-05T11:00:00+00:00",
                    "end": "2026-08-05T12:00:00+00:00",
                    "limit": 1,
                }
            )
        )
        assert len(timeline["events"]) == 1
        assert timeline["events"][0]["event_type"] == "health_note"

        with pytest.raises(HomeAssistantError, match="status is invalid"):
            await _async_handle_get_tasks(_call({"status": "bad"}))
        with pytest.raises(
            HomeAssistantError, match="limit must be a positive integer"
        ):
            await _async_handle_get_tasks(_call({"limit": 0}))
        with pytest.raises(HomeAssistantError, match="event_type is invalid"):
            await _async_handle_get_timeline(_call({"event_type": "bad"}))
        with pytest.raises(
            HomeAssistantError, match="limit must be a positive integer"
        ):
            await _async_handle_get_timeline(_call({"limit": False}))

    asyncio.run(_run())
