"""Pure-Python tests for ReptileCare service helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from custom_components.reptilecare.domain.care_plan import CarePlanScheduleUnit
from custom_components.reptilecare.domain.care_task import CareTask
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.services import (
    _actor_id,
    _attachments,
    _field_present,
    _generation_parameters,
    _json_object,
    _json_value,
    _optional_date,
    _optional_datetime,
    _optional_text,
    _parse_date,
    _parse_datetime,
    _parse_reminder,
    _parse_reptile_identifier,
    _parse_schedule,
    _parse_timedelta,
    _require_text,
    _serialize_care_task,
    _serialize_event,
    _serialize_preview_task,
)

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"


def _pixel() -> Reptile:
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )


async def _reptile_runtime() -> SimpleNamespace:
    repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await repository.async_load()
    await repository.async_add(_pixel())
    return SimpleNamespace(reptile_repository=repository)


def test_parse_date_and_datetime_validation() -> None:
    """Date and datetime parsing normalize valid input and reject invalid input."""
    assert _parse_date("2026-08-05", "effective_date") == date(2026, 8, 5)
    assert _parse_date(date(2026, 8, 5), "effective_date") == date(2026, 8, 5)
    assert _parse_datetime(
        "2026-08-05T12:00:00+00:00",
        "timestamp",
    ) == datetime(2026, 8, 5, 12, tzinfo=UTC)
    assert _parse_datetime(
        datetime(2026, 8, 5, 12, tzinfo=UTC),
        "timestamp",
    ) == datetime(2026, 8, 5, 12, tzinfo=UTC)

    with pytest.raises(Exception, match="effective_date must be an ISO date"):
        _parse_date("bad-date", "effective_date")
    with pytest.raises(Exception, match="effective_date must be an ISO date"):
        _parse_date(123, "effective_date")
    with pytest.raises(Exception, match="timestamp must be an ISO datetime"):
        _parse_datetime("bad-datetime", "timestamp")
    with pytest.raises(Exception, match="timestamp must be timezone-aware"):
        _parse_datetime("2026-08-05T12:00:00", "timestamp")


def test_parse_schedule_and_reminder_validation() -> None:
    """Schedule and reminder helper parsing reuse the domain rules."""
    schedule = _parse_schedule(
        {"schedule_type": "interval", "every": 2, "unit": "days"}
    )
    assert schedule.every == 2
    assert schedule.unit is CarePlanScheduleUnit.DAYS

    reminder = _parse_reminder(
        {
            "enabled": True,
            "lead_time": {"amount": 4, "unit": "hours"},
            "repeat_policy": "once",
            "metadata": {"channel": "mobile"},
        }
    )
    assert reminder.enabled is True
    assert reminder.lead_time is not None
    assert reminder.lead_time.amount == 4

    with pytest.raises(Exception, match="invalid schedule"):
        _parse_schedule({"schedule_type": "interval", "every": 0, "unit": "days"})
    with pytest.raises(Exception, match="schedule must be an object"):
        _parse_schedule("daily")
    with pytest.raises(Exception, match="schedule_type must be 'interval'"):
        _parse_schedule({"schedule_type": "cron", "every": 1, "unit": "days"})
    with pytest.raises(Exception, match="schedule is missing key: every"):
        _parse_schedule({"schedule_type": "interval", "unit": "days"})
    with pytest.raises(Exception, match="invalid reminder_configuration"):
        _parse_reminder({"enabled": True})
    with pytest.raises(Exception, match="reminder lead_time must be an object"):
        _parse_reminder({"lead_time": "soon"})
    with pytest.raises(Exception, match="reminder lead_time is missing key: amount"):
        _parse_reminder({"lead_time": {"unit": "hours"}})


def test_parse_timedelta_rejects_unknown_keys() -> None:
    """Duration parsing rejects unsupported units."""
    delta = _parse_timedelta({"days": 2, "hours": 6}, "horizon_duration")
    assert delta.days == 2
    assert delta.seconds == 21600

    with pytest.raises(Exception, match="unsupported keys"):
        _parse_timedelta({"months": 1}, "horizon_duration")
    with pytest.raises(Exception, match="must not be negative"):
        _parse_timedelta({"hours": -1}, "horizon_duration")
    with pytest.raises(Exception, match="must be numeric"):
        _parse_timedelta({"hours": True}, "horizon_duration")


def test_serialize_event_and_task() -> None:
    """Service serializers return stable JSON-compatible values."""
    care_plan_id = str(uuid4())
    task = CareTask(
        reptile_id=PIXEL_ID,
        care_plan_id=care_plan_id,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        due_at=datetime(2026, 8, 7, 12, tzinfo=UTC),
        generation_key="task-key",
        created_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
    )
    serialized_task = _serialize_care_task(
        task, now=datetime(2026, 8, 5, 12, tzinfo=UTC)
    )
    assert serialized_task["due_state"] == "upcoming"
    assert serialized_task["attachment_references"] == []
    preview_task = _serialize_preview_task(task)
    assert "task_id" not in preview_task

    event = CareEvent(
        reptile_id=PIXEL_ID,
        event_type=CareEventType.HEALTH_NOTE,
        timestamp=datetime(2026, 8, 5, 12, tzinfo=UTC),
        context={"observation": "active"},
        attachment_references=("photo-1",),
        metadata={"notes": "steady appetite"},
    )
    serialized_event = _serialize_event(event)
    assert serialized_event["event_type"] == "health_note"
    assert serialized_event["context"]["observation"] == "active"
    assert serialized_event["metadata"]["notes"] == "steady appetite"
    assert serialized_event["attachment_references"] == ["photo-1"]


def test_parse_reptile_identifier_rules() -> None:
    """Identifier resolution supports UUID or slug and optional UUID precedence."""

    async def _run() -> None:
        runtime = await _reptile_runtime()
        assert (
            _parse_reptile_identifier(
                runtime,
                SimpleNamespace(data={"slug": "pixel"}),
            )
            == PIXEL_ID
        )
        assert (
            _parse_reptile_identifier(
                runtime,
                SimpleNamespace(data={"reptile_id": PIXEL_ID, "slug": "new-slug"}),
                reptile_id_precedence=True,
            )
            == PIXEL_ID
        )
        with pytest.raises(Exception, match="Provide exactly one"):
            _parse_reptile_identifier(
                runtime,
                SimpleNamespace(data={}),
            )
        with pytest.raises(Exception, match="reptile slug not found: beans"):
            _parse_reptile_identifier(
                runtime,
                SimpleNamespace(data={"slug": "beans"}),
            )

    import asyncio

    asyncio.run(_run())


def test_generation_parameters_reject_conflicting_reptile_and_plan() -> None:
    """Generation parameter parsing rejects mismatched reptile and care-plan filters."""

    async def _run() -> None:
        runtime = await _reptile_runtime()
        runtime.care_plan_repository = SimpleNamespace(
            get=lambda _: SimpleNamespace(care_plan_id="plan-1", reptile_id="other-id")
        )
        with pytest.raises(Exception, match="does not belong to reptile"):
            _generation_parameters(
                runtime,
                SimpleNamespace(
                    data={
                        "reptile_id": PIXEL_ID,
                        "care_plan_id": "plan-1",
                    }
                ),
            )

    import asyncio

    asyncio.run(_run())


def test_text_json_and_attachment_helpers() -> None:
    """Service helper validation keeps user-facing payloads bounded and typed."""
    call = SimpleNamespace(
        data={
            "name": "  Pixel  ",
            "nickname": "  Pebble  ",
            "payload": {"a": 1, "items": [True, "x"]},
            "attachments": [" photo-1 ", "photo-2"],
            "when": "2026-08-05",
            "timestamp": "2026-08-05T12:00:00+00:00",
        },
        context=SimpleNamespace(user_id="keeper-1"),
    )

    assert _field_present(call, "name") is True
    assert _require_text(call, "name") == "Pixel"
    assert _optional_text(call, "nickname") == "Pebble"
    assert _optional_date(call, "when") == date(2026, 8, 5)
    assert _optional_datetime(call, "timestamp") == datetime(2026, 8, 5, 12, tzinfo=UTC)
    assert _actor_id(call) == "keeper-1"
    assert dict(_json_object(call, "payload"))["a"] == 1
    assert _attachments(call, "attachments") == ("photo-1", "photo-2")

    normalized = _json_value({"nested": [1, {"ok": True}]}, "payload")
    assert dict(normalized)["nested"][1]["ok"] is True

    with pytest.raises(Exception, match="title must be a non-empty string"):
        _require_text(SimpleNamespace(data={"title": "   "}), "title")
    with pytest.raises(
        Exception, match="nickname must be a non-empty string when provided"
    ):
        _optional_text(SimpleNamespace(data={"nickname": ""}), "nickname")
    with pytest.raises(Exception, match="payload numbers must be finite"):
        _json_value(float("inf"), "payload")
    with pytest.raises(Exception, match="payload keys must be strings"):
        _json_value({1: "x"}, "payload")
    with pytest.raises(
        Exception, match="payload must contain only JSON-compatible values"
    ):
        _json_value({1, 2}, "payload")
    with pytest.raises(Exception, match="payload must be an object"):
        _json_object(SimpleNamespace(data={"payload": []}), "payload")
    with pytest.raises(Exception, match="attachments must be an array of strings"):
        _attachments(SimpleNamespace(data={"attachments": "photo-1"}), "attachments")
    with pytest.raises(Exception, match="attachments must contain non-empty strings"):
        _attachments(SimpleNamespace(data={"attachments": ["", "ok"]}), "attachments")


def test_generation_parameters_success_and_window_validation() -> None:
    """Generation parameter parsing normalizes optional windows."""

    async def _run() -> None:
        runtime = await _reptile_runtime()
        runtime.care_plan_repository = SimpleNamespace(
            get=lambda _: SimpleNamespace(care_plan_id="plan-1", reptile_id=PIXEL_ID)
        )

        reptile_id, care_plan_id, now, look_ahead = _generation_parameters(
            runtime,
            SimpleNamespace(
                data={
                    "slug": "pixel",
                    "care_plan_id": "plan-1",
                    "now": "2026-08-05T12:00:00+00:00",
                    "horizon_duration": {"days": 2, "hours": 6},
                }
            ),
        )
        assert reptile_id == PIXEL_ID
        assert care_plan_id == "plan-1"
        assert now == datetime(2026, 8, 5, 12, tzinfo=UTC)
        assert look_ahead == datetime(2026, 8, 7, 18, tzinfo=UTC) - now

        _, _, _, bounded_look_ahead = _generation_parameters(
            runtime,
            SimpleNamespace(
                data={
                    "slug": "pixel",
                    "care_plan_id": "plan-1",
                    "now": "2026-08-05T12:00:00+00:00",
                    "horizon_end": "2026-08-06T00:00:00+00:00",
                }
            ),
        )
        assert bounded_look_ahead == timedelta(hours=12)

        with pytest.raises(Exception, match="horizon_end must not be earlier than now"):
            _generation_parameters(
                runtime,
                SimpleNamespace(
                    data={
                        "slug": "pixel",
                        "care_plan_id": "plan-1",
                        "now": "2026-08-05T12:00:00+00:00",
                        "horizon_end": "2026-08-05T11:59:59+00:00",
                    }
                ),
            )

    import asyncio

    asyncio.run(_run())
