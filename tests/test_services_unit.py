"""Pure-Python tests for ReptileCare service handlers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanScheduleUnit,
    IntervalSchedule,
)
from custom_components.reptilecare.domain.care_task import CareTask, CareTaskStatus
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.services import (
    _async_handle_generate_tasks,
    _async_handle_get_tasks,
    _async_handle_get_timeline,
    _async_handle_log_event,
    _async_handle_preview_task_generation,
    _async_handle_system_health,
    _runtime_entry,
    async_unregister_services,
)
from custom_components.reptilecare.task_generation import (
    TaskGenerationPreviewResult,
    TaskGenerationResult,
)

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "660e8400-e29b-41d4-a716-446655440000"
TASK_ID_1 = "770e8400-e29b-41d4-a716-446655440000"
TASK_ID_2 = "880e8400-e29b-41d4-a716-446655440000"
TASK_ID_3 = "990e8400-e29b-41d4-a716-446655440000"


def _pixel() -> Reptile:
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )


async def _reptile_repository() -> ReptileRepository:
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    await repository.async_add(_pixel())
    return repository


def _task(
    *,
    task_id: str,
    due_at: datetime,
    status: CareTaskStatus = CareTaskStatus.PENDING,
    reptile_id: str = PIXEL_ID,
    care_plan_id: str = PLAN_ID,
) -> CareTask:
    return CareTask(
        task_id=task_id,
        reptile_id=reptile_id,
        care_plan_id=care_plan_id,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        due_at=due_at,
        generation_key=f"gen-{task_id}",
        created_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
        status=status,
        completed_at=(
            None
            if status is CareTaskStatus.PENDING
            else datetime(2026, 8, 5, 12, tzinfo=UTC)
        ),
    )


def _call(data: dict[str, object], *, hass: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        hass=SimpleNamespace() if hass is None else hass,
        context=SimpleNamespace(user_id="keeper-1"),
    )


def test_runtime_entry_and_unregister_services() -> None:
    """Runtime entry lookup validates loaded entries and unregister is selective."""
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: []),
    )
    with pytest.raises(HomeAssistantError, match="ReptileCare is not set up"):
        _runtime_entry(hass)

    loaded = SimpleNamespace(state=ConfigEntryState.LOADED, runtime_data=object())
    second = SimpleNamespace(state=ConfigEntryState.LOADED, runtime_data=object())
    hass.config_entries = SimpleNamespace(async_entries=lambda domain: [loaded, second])
    with pytest.raises(
        HomeAssistantError, match="requires exactly one active config entry"
    ):
        _runtime_entry(hass)

    removed: list[str] = []
    hass.services = SimpleNamespace(
        has_service=lambda domain, service: service in {"create_reptile", "get_tasks"},
        async_remove=lambda domain, service: removed.append(service),
    )
    async_unregister_services(hass)
    assert removed == ["create_reptile", "get_tasks"]


def test_generate_and_preview_handlers(monkeypatch) -> None:
    """Generation handlers serialize created, existing, skipped, and warning data."""

    async def _run() -> None:
        reptile_repository = await _reptile_repository()
        plan = CarePlan(
            care_plan_id=PLAN_ID,
            reptile_id=PIXEL_ID,
            task_template_id="builtin:feed_fruit",
            workflow_id="builtin:feeding_cycle",
            display_name="Feed Fruit",
            schedule=IntervalSchedule(every=2, unit=CarePlanScheduleUnit.DAYS),
            effective_date=datetime(2026, 8, 5, tzinfo=UTC).date(),
        )
        created = _task(
            task_id=TASK_ID_1,
            due_at=datetime(2026, 8, 6, 0, tzinfo=UTC),
        )
        existing = _task(
            task_id=TASK_ID_2,
            due_at=datetime(2026, 8, 7, 0, tzinfo=UTC),
        )
        runtime = SimpleNamespace(
            reptile_repository=reptile_repository,
            care_plan_repository=SimpleNamespace(get=lambda _: plan),
            care_task_generator=SimpleNamespace(
                async_generate=lambda **kwargs: asyncio.sleep(
                    0,
                    result=TaskGenerationResult(
                        created_task_ids=(TASK_ID_1,),
                        existing_task_ids=(TASK_ID_2,),
                        skipped_plan_ids=("plan-skip",),
                        warnings=("warn-1",),
                        errors={"plan-err": "missing template"},
                    ),
                ),
                async_preview=lambda **kwargs: asyncio.sleep(
                    0,
                    result=TaskGenerationPreviewResult(
                        would_create=(created,),
                        already_exists=(existing,),
                        skipped_plan_ids=("plan-skip",),
                        warnings=("warn-1",),
                        errors={"plan-err": "missing template"},
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.services._runtime",
            lambda hass: runtime,
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.services.async_notify_runtime_updated",
            lambda hass: None,
        )

        generate = await _async_handle_generate_tasks(
            _call(
                {
                    "slug": "pixel",
                    "care_plan_id": PLAN_ID,
                    "now": "2026-08-05T12:00:00+00:00",
                    "horizon_duration": {"days": 1},
                }
            )
        )
        assert generate["created_task_ids"] == [TASK_ID_1]
        assert generate["existing_task_ids"] == [TASK_ID_2]
        assert generate["errors"] == {"plan-err": "missing template"}

        preview = await _async_handle_preview_task_generation(
            _call(
                {
                    "slug": "pixel",
                    "care_plan_id": PLAN_ID,
                    "now": "2026-08-05T12:00:00+00:00",
                    "horizon_duration": {"days": 1},
                }
            )
        )
        assert len(preview["would_create"]) == 1
        assert preview["already_exists"][0]["task_id"] == TASK_ID_2
        assert preview["warnings"] == ["warn-1", "care plan plan-err: missing template"]

    asyncio.run(_run())


def test_get_tasks_and_timeline_handlers(monkeypatch) -> None:
    """Query handlers filter by identity, time window, enum parsing, and limit."""

    async def _run() -> None:
        reptile_repository = await _reptile_repository()
        now = datetime(2026, 8, 5, 12, tzinfo=UTC)
        tasks = (
            _task(task_id=TASK_ID_1, due_at=now + timedelta(hours=3)),
            _task(task_id=TASK_ID_2, due_at=now - timedelta(hours=2)),
            _task(
                task_id=TASK_ID_3,
                due_at=now - timedelta(days=1),
                status=CareTaskStatus.COMPLETED,
            ),
        )
        events = (
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
        )
        runtime = SimpleNamespace(
            reptile_repository=reptile_repository,
            care_task_repository=SimpleNamespace(all=lambda: tasks),
            timeline=SimpleNamespace(all_events=lambda: events),
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

        result = await _async_handle_get_tasks(
            _call(
                {
                    "slug": "pixel",
                    "due_state": "upcoming",
                    "due_after": "2026-08-05T12:00:00+00:00",
                    "limit": 1,
                }
            )
        )
        assert [task["task_id"] for task in result["tasks"]] == [TASK_ID_1]

        terminal = await _async_handle_get_tasks(
            _call(
                {
                    "slug": "pixel",
                    "status": "completed",
                    "include_terminal": True,
                    "due_before": "2026-08-05T12:00:00+00:00",
                }
            )
        )
        assert [task["task_id"] for task in terminal["tasks"]] == [TASK_ID_3]

        with pytest.raises(HomeAssistantError, match="status is invalid"):
            await _async_handle_get_tasks(_call({"status": "bad"}))
        with pytest.raises(
            HomeAssistantError, match="limit must be a positive integer"
        ):
            await _async_handle_get_tasks(_call({"limit": 0}))

        filtered_events = await _async_handle_get_timeline(
            _call(
                {
                    "slug": "pixel",
                    "event_type": "health_note",
                    "start": "2026-08-05T11:00:00+00:00",
                    "end": "2026-08-05T12:00:00+00:00",
                    "limit": 1,
                }
            )
        )
        assert len(filtered_events["events"]) == 1
        assert filtered_events["events"][0]["event_type"] == "health_note"

        with pytest.raises(HomeAssistantError, match="event_type is invalid"):
            await _async_handle_get_timeline(_call({"event_type": "bad"}))
        with pytest.raises(
            HomeAssistantError, match="limit must be a positive integer"
        ):
            await _async_handle_get_timeline(_call({"limit": False}))

    asyncio.run(_run())


def test_log_event_and_system_health_handlers(monkeypatch) -> None:
    """Event logging and system health handlers serialize stable application data."""

    async def _run() -> None:
        reptile_repository = await _reptile_repository()
        appended: list[CareEvent] = []
        runtime = SimpleNamespace(
            reptile_repository=reptile_repository,
            event_store=SimpleNamespace(
                async_append_event=lambda event: asyncio.sleep(
                    0,
                    result=appended.append(event),
                )
            ),
            coordinator=SimpleNamespace(
                async_refresh=lambda: asyncio.sleep(0),
            ),
            species_profiles=SimpleNamespace(all=lambda: ("species",)),
            care_plan_repository=SimpleNamespace(all=lambda: ("plan",)),
            task_templates=SimpleNamespace(all=lambda: ("template",)),
            workflow_graphs=SimpleNamespace(all=lambda: ("workflow",)),
            care_task_repository=SimpleNamespace(
                pending=lambda: ("pending-1", "pending-2"),
                for_status=lambda status: (
                    ("done",) if status is CareTaskStatus.COMPLETED else ()
                ),
            ),
            timeline=SimpleNamespace(
                all_events=lambda: tuple(appended),
            ),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.services._runtime",
            lambda hass: runtime,
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.services.async_notify_runtime_updated",
            lambda hass: None,
        )

        event_result = await _async_handle_log_event(
            _call(
                {
                    "slug": "pixel",
                    "event_type": "health_note",
                    "timestamp": "2026-08-05T12:00:00+00:00",
                    "context": {"observation": "alert"},
                    "notes": "steady appetite",
                    "environmental_context": {"humidity": 68},
                    "attachment_references": ["photo-1"],
                }
            )
        )
        assert event_result["care_event"]["event_type"] == "health_note"
        assert event_result["care_event"]["metadata"]["notes"] == "steady appetite"

        health = await _async_handle_system_health(_call({}))
        assert health["species_profile_count"] == 1
        assert health["pending_task_count"] == 2
        assert health["completed_task_count"] == 1
        assert health["care_event_count"] == 1

    asyncio.run(_run())
