"""Integration tests for ReptileCare Home Assistant services."""

from __future__ import annotations

from datetime import UTC, date, datetime

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME
from custom_components.reptilecare.version import INTEGRATION_VERSION


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def _call_service(
    hass: HomeAssistant,
    service: str,
    data: dict[str, object],
    *,
    user_id: str | None = None,
) -> dict[str, object]:
    return await hass.services.async_call(
        DOMAIN,
        service,
        data,
        blocking=True,
        return_response=True,
        context=Context(user_id=user_id),
    )


async def _create_pixel(hass: HomeAssistant) -> dict[str, object]:
    response = await _call_service(
        hass,
        "create_reptile",
        {
            "display_name": "Pixel",
            "slug": "pixel",
            "species_profile_id": "builtin:gargoyle_gecko",
        },
    )
    return response["reptile"]  # type: ignore[return-value]


async def _create_feeding_plan(
    hass: HomeAssistant,
    *,
    reptile_id: str | None = None,
    slug: str | None = None,
    effective_date: date = date(2026, 8, 5),
) -> dict[str, object]:
    data: dict[str, object] = {
        "task_template_id": "builtin:feed_fruit",
        "workflow_id": "builtin:feeding_cycle",
        "display_name": "Feed Fruit",
        "effective_date": effective_date,
        "schedule": {"schedule_type": "interval", "every": 2, "unit": "days"},
    }
    if reptile_id is not None:
        data["reptile_id"] = reptile_id
    if slug is not None:
        data["slug"] = slug
    response = await _call_service(hass, "create_care_plan", data)
    return response["care_plan"]  # type: ignore[return-value]


async def test_service_registration_reload_and_unload(
    hass: HomeAssistant,
) -> None:
    """Services register on setup, survive reload, and disappear on unload."""
    entry = await _setup_entry(hass)

    assert hass.services.has_service(DOMAIN, "create_reptile")
    assert hass.services.has_service(DOMAIN, "resolve_task")
    assert hass.services.has_service(DOMAIN, "get_timeline")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "create_reptile")
    assert hass.services.has_service(DOMAIN, "get_tasks")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "create_reptile")
    assert not hass.services.has_service(DOMAIN, "get_timeline")


async def test_create_and_update_reptile_by_slug(
    hass: HomeAssistant,
) -> None:
    """Reptile services resolve slugs and preserve stable identifiers."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)

    response = await _call_service(
        hass,
        "update_reptile",
        {
            "slug": "pixel",
            "display_name": "Pixel 🦎",
            "notes": "Moved to display enclosure",
        },
    )
    updated = response["reptile"]

    assert updated["reptile_id"] == pixel["reptile_id"]
    assert updated["slug"] == "pixel"
    assert updated["display_name"] == "Pixel 🦎"
    assert updated["notes"] == "Moved to display enclosure"

    renamed = await _call_service(
        hass,
        "update_reptile",
        {
            "reptile_id": pixel["reptile_id"],
            "slug": "pixel-main",
        },
    )
    assert renamed["reptile"]["slug"] == "pixel-main"


async def test_duplicate_slug_and_missing_identifier_fail_clearly(
    hass: HomeAssistant,
) -> None:
    """Service validation rejects duplicate slugs and missing stable identity."""
    await _setup_entry(hass)
    await _create_pixel(hass)

    with pytest.raises(HomeAssistantError, match="duplicate reptile slug: pixel"):
        await _call_service(
            hass,
            "create_reptile",
            {
                "display_name": "Beans",
                "slug": "pixel",
                "species_profile_id": "builtin:gargoyle_gecko",
            },
        )

    with pytest.raises(
        HomeAssistantError, match="Provide exactly one of reptile_id or slug"
    ):
        await _call_service(
            hass,
            "update_reptile",
            {"display_name": "Pixel", "notes": "No stable identifier"},
        )


async def test_create_care_plan_and_invalid_reference(
    hass: HomeAssistant,
) -> None:
    """Care plan services validate referenced reptile, template, and workflow IDs."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, reptile_id=pixel["reptile_id"])

    assert plan["reptile_id"] == pixel["reptile_id"]
    assert plan["task_template_id"] == "builtin:feed_fruit"
    assert plan["workflow_id"] == "builtin:feeding_cycle"

    with pytest.raises(
        HomeAssistantError,
        match="reptile slug not found: missing",
    ):
        await _call_service(
            hass,
            "create_care_plan",
            {
                "slug": "missing",
                "task_template_id": "builtin:feed_fruit",
                "workflow_id": "builtin:feeding_cycle",
                "display_name": "Invalid",
                "schedule": {
                    "schedule_type": "interval",
                    "every": 2,
                    "unit": "days",
                },
            },
        )


async def test_enable_disable_reptile_and_care_plan(
    hass: HomeAssistant,
) -> None:
    """Enable and disable services return updated serialized records."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, reptile_id=pixel["reptile_id"])

    reptile = await _call_service(
        hass, "disable_reptile", {"reptile_id": pixel["reptile_id"]}
    )
    assert reptile["reptile"]["enabled"] is False

    reptile = await _call_service(hass, "enable_reptile", {"slug": "pixel"})
    assert reptile["reptile"]["enabled"] is True

    care_plan = await _call_service(
        hass, "disable_care_plan", {"care_plan_id": plan["care_plan_id"]}
    )
    assert care_plan["care_plan"]["enabled"] is False

    care_plan = await _call_service(
        hass, "enable_care_plan", {"care_plan_id": plan["care_plan_id"]}
    )
    assert care_plan["care_plan"]["enabled"] is True


async def test_generate_tasks_is_idempotent_and_filterable(
    hass: HomeAssistant,
) -> None:
    """Task generation returns structured idempotent results."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, slug="pixel")

    first = await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "reptile_id": pixel["reptile_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    second = await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "slug": "pixel",
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )

    assert len(first["created_task_ids"]) == 1
    assert first["existing_task_ids"] == []
    assert second["created_task_ids"] == []
    assert second["existing_task_ids"] == first["created_task_ids"]
    assert second["skipped_plan_ids"] == []
    assert second["errors"] == {}


async def test_preview_task_generation_is_non_persisting(
    hass: HomeAssistant,
) -> None:
    """Preview generation reuses production logic without writing tasks."""
    await _setup_entry(hass)
    await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, slug="pixel")

    preview = await _call_service(
        hass,
        "preview_task_generation",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    assert len(preview["would_create"]) == 1
    assert preview["already_exists"] == []
    assert preview["skipped"] == []
    assert preview["warnings"] == []
    assert "task_id" not in preview["would_create"][0]

    tasks = await _call_service(
        hass,
        "get_tasks",
        {"slug": "pixel", "include_terminal": True},
    )
    assert tasks["tasks"] == []

    generated = await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    assert len(generated["created_task_ids"]) == 1

    preview_after = await _call_service(
        hass,
        "preview_task_generation",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    assert preview_after["would_create"] == []
    assert len(preview_after["already_exists"]) == 1


async def test_resolve_task_returns_event_follow_up_and_actor(
    hass: HomeAssistant,
) -> None:
    """Task resolution delegates to CareEngine and preserves actor attribution."""
    await _setup_entry(hass)
    await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, slug="pixel")
    generation = await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    task_id = generation["created_task_ids"][0]

    result = await _call_service(
        hass,
        "resolve_task",
        {
            "task_id": task_id,
            "action": "complete",
            "outcome_id": "ate_normally",
            "outcome_metadata": {"food_used": "papaya", "quantity": 30},
            "notes": "Finished meal",
            "environmental_context": {"temperature_f": 78},
        },
        user_id="keeper-1",
    )

    assert result["task"]["status"] == "completed"
    assert result["task"]["resolution_actor_id"] == "keeper-1"
    assert result["care_event"]["event_type"] == "feeding"
    assert result["care_event"]["actor_id"] == "keeper-1"
    assert result["care_event"]["source"] == "home_assistant_service"
    assert result["care_event"]["context"]["quantity"] == 30
    assert len(result["created_follow_up_tasks"]) == 1
    assert (
        result["created_follow_up_tasks"][0]["task_template_id"]
        == "builtin:remove_food"
    )
    assert result["existing_follow_up_tasks"] == []
    assert result["replayed_existing_result"] is False

    replay = await _call_service(
        hass,
        "resolve_task",
        {
            "task_id": task_id,
            "action": "complete",
            "outcome_id": "ate_normally",
            "outcome_metadata": {"food_used": "papaya", "quantity": 30},
            "notes": "Finished meal",
            "environmental_context": {"temperature_f": 78},
        },
        user_id="keeper-1",
    )
    assert replay["replayed_existing_result"] is True
    assert replay["created_follow_up_tasks"] == []
    assert len(replay["existing_follow_up_tasks"]) == 1


async def test_resolve_task_without_user_context_preserves_service_source(
    hass: HomeAssistant,
) -> None:
    """Automation-style calls may omit actor attribution while keeping a source."""
    await _setup_entry(hass)
    await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, slug="pixel")
    generation = await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    task_id = generation["created_task_ids"][0]

    result = await _call_service(
        hass,
        "resolve_task",
        {"task_id": task_id, "action": "skip"},
    )

    assert result["task"]["resolution_actor_id"] is None
    assert result["task"]["resolution_source"] == "home_assistant_service"
    assert result["care_event"]["actor_id"] is None
    assert result["care_event"]["source"] == "home_assistant_service"


async def test_resolve_task_conflicting_transition_fails(
    hass: HomeAssistant,
) -> None:
    """Conflicting second terminal transitions fail with a clear service error."""
    await _setup_entry(hass)
    await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, slug="pixel")
    generation = await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    task_id = generation["created_task_ids"][0]

    await _call_service(
        hass,
        "resolve_task",
        {"task_id": task_id, "action": "skip"},
    )

    with pytest.raises(HomeAssistantError, match="already resolved"):
        await _call_service(
            hass,
            "resolve_task",
            {"task_id": task_id, "action": "cancel"},
        )


async def test_log_event_and_query_services(
    hass: HomeAssistant,
) -> None:
    """Manual event logging and query services return stable JSON-compatible data."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)

    event = await _call_service(
        hass,
        "log_event",
        {
            "reptile_id": pixel["reptile_id"],
            "event_type": "health_note",
            "timestamp": datetime(2026, 8, 4, 15, tzinfo=UTC),
            "context": {"observation": "Alert and active"},
            "notes": "Observed normal behavior",
            "environmental_context": {"humidity": 68},
        },
        user_id="keeper-2",
    )

    assert event["care_event"]["event_type"] == "health_note"
    assert event["care_event"]["actor_id"] == "keeper-2"
    assert event["care_event"]["source"] == "home_assistant_service"
    assert event["care_event"]["metadata"]["notes"] == "Observed normal behavior"

    timeline = await _call_service(
        hass,
        "get_timeline",
        {
            "slug": "pixel",
            "event_type": "health_note",
            "start": datetime(2026, 8, 4, 0, tzinfo=UTC),
            "end": datetime(2026, 8, 5, 0, tzinfo=UTC),
            "limit": 10,
        },
    )
    assert len(timeline["events"]) == 1
    assert timeline["events"][0]["reptile_id"] == pixel["reptile_id"]


async def test_get_tasks_filters_due_state_and_limit(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task queries support reptile resolution, due-state projection, and limits."""
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(
        "custom_components.reptilecare.services.datetime",
        FixedDateTime,
    )

    await _setup_entry(hass)
    await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, slug="pixel")
    await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": now.isoformat(),
            "horizon_duration": {"days": 5},
        },
    )

    tasks = await _call_service(
        hass,
        "get_tasks",
        {
            "slug": "pixel",
            "due_state": "upcoming",
            "limit": 1,
        },
    )

    assert len(tasks["tasks"]) == 1
    assert tasks["tasks"][0]["status"] == "pending"
    assert tasks["tasks"][0]["due_state"] == "upcoming"


async def test_create_care_plan_rejects_invalid_schedule(
    hass: HomeAssistant,
) -> None:
    """Invalid schedule payloads fail with a clear service error."""
    await _setup_entry(hass)
    await _create_pixel(hass)

    with pytest.raises(HomeAssistantError, match="invalid schedule"):
        await _call_service(
            hass,
            "create_care_plan",
            {
                "slug": "pixel",
                "task_template_id": "builtin:feed_fruit",
                "workflow_id": "builtin:feeding_cycle",
                "display_name": "Feed Fruit",
                "schedule": {
                    "schedule_type": "interval",
                    "every": 0,
                    "unit": "days",
                },
            },
        )


async def test_system_health_reports_runtime_counts(
    hass: HomeAssistant,
) -> None:
    """System health returns stable high-level runtime diagnostics."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    plan = await _create_feeding_plan(hass, reptile_id=pixel["reptile_id"])
    await _call_service(
        hass,
        "generate_tasks",
        {
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    await _call_service(
        hass,
        "log_event",
        {
            "slug": "pixel",
            "event_type": "health_note",
            "timestamp": datetime(2026, 8, 5, 13, tzinfo=UTC),
            "context": {"observation": "calm"},
        },
    )

    health = await _call_service(hass, "system_health", {})

    assert health["integration_version"] == INTEGRATION_VERSION
    assert health["schema_version"]["reptiles"] == 1
    assert health["species_profile_count"] >= 1
    assert health["reptile_count"] == 1
    assert health["care_plan_count"] == 1
    assert health["task_template_count"] >= 1
    assert health["workflow_graph_count"] >= 1
    assert health["pending_task_count"] == 1
    assert health["completed_task_count"] == 0
    assert health["care_event_count"] == 1
