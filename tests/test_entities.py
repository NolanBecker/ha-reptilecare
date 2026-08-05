"""Integration tests for ReptileCare entity platforms."""

from __future__ import annotations

from datetime import UTC, date, datetime

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME


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
) -> dict[str, object]:
    return await hass.services.async_call(
        DOMAIN,
        service,
        data,
        blocking=True,
        return_response=True,
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


async def _create_plan(hass: HomeAssistant) -> dict[str, object]:
    response = await _call_service(
        hass,
        "create_care_plan",
        {
            "slug": "pixel",
            "task_template_id": "builtin:feed_fruit",
            "workflow_id": "builtin:feeding_cycle",
            "display_name": "Feed Fruit",
            "effective_date": date(2026, 8, 5),
            "schedule": {"schedule_type": "interval", "every": 2, "unit": "days"},
        },
    )
    return response["care_plan"]  # type: ignore[return-value]


def _entity_id(
    entity_registry: er.EntityRegistry,
    platform: str,
    unique_id: str,
) -> str:
    entity_id = entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


async def test_entities_create_one_device_per_reptile_and_stable_unique_ids(
    hass: HomeAssistant,
) -> None:
    """Per-reptile entities attach to one stable reptile device."""
    entry = await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    reptile_id = pixel["reptile_id"]
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    pending_entity_id = _entity_id(
        entity_registry, "sensor", f"{reptile_id}_pending_task_count"
    )
    next_entity_id = _entity_id(entity_registry, "sensor", f"{reptile_id}_next_task")
    last_event_entity_id = _entity_id(
        entity_registry, "sensor", f"{reptile_id}_last_event"
    )
    due_entity_id = _entity_id(
        entity_registry, "binary_sensor", f"{reptile_id}_care_due"
    )
    overdue_entity_id = _entity_id(
        entity_registry, "binary_sensor", f"{reptile_id}_overdue_care"
    )
    pending_binary_entity_id = _entity_id(
        entity_registry, "binary_sensor", f"{reptile_id}_pending_care"
    )
    button_entity_id = _entity_id(
        entity_registry, "button", f"{reptile_id}_generate_tasks"
    )

    device = device_registry.async_get_device(identifiers={(DOMAIN, reptile_id)})
    assert device is not None
    assert device.name == "Pixel"
    assert device.model == "Gargoyle Gecko"
    assert device.manufacturer == "ReptileCare"

    for entity_id in (
        pending_entity_id,
        next_entity_id,
        last_event_entity_id,
        due_entity_id,
        overdue_entity_id,
        pending_binary_entity_id,
        button_entity_id,
    ):
        entity_entry = entity_registry.async_get(entity_id)
        assert entity_entry is not None
        assert entity_entry.device_id == device.id

    renamed = await _call_service(
        hass,
        "update_reptile",
        {
            "reptile_id": reptile_id,
            "display_name": "Pixel Prime",
            "slug": "pixel-main",
        },
    )
    assert renamed["reptile"]["reptile_id"] == reptile_id
    await hass.async_block_till_done()

    same_device = device_registry.async_get_device(identifiers={(DOMAIN, reptile_id)})
    assert same_device is not None
    assert same_device.id == device.id
    assert same_device.name == "Pixel Prime"
    assert (
        entry.runtime_data.entity_projection.species_model(reptile_id)
        == "Gargoyle Gecko"
    )


async def test_entity_states_update_from_services_and_button(
    hass: HomeAssistant,
) -> None:
    """Task and event services refresh entity projections without restart."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    reptile_id = pixel["reptile_id"]
    plan = await _create_plan(hass)
    entity_registry = er.async_get(hass)

    pending_entity_id = _entity_id(
        entity_registry, "sensor", f"{reptile_id}_pending_task_count"
    )
    next_entity_id = _entity_id(entity_registry, "sensor", f"{reptile_id}_next_task")
    last_event_entity_id = _entity_id(
        entity_registry, "sensor", f"{reptile_id}_last_event"
    )
    due_entity_id = _entity_id(
        entity_registry, "binary_sensor", f"{reptile_id}_care_due"
    )
    overdue_entity_id = _entity_id(
        entity_registry, "binary_sensor", f"{reptile_id}_overdue_care"
    )
    pending_binary_entity_id = _entity_id(
        entity_registry, "binary_sensor", f"{reptile_id}_pending_care"
    )
    button_entity_id = _entity_id(
        entity_registry, "button", f"{reptile_id}_generate_tasks"
    )

    assert hass.states.get(pending_entity_id).state == "0"
    assert hass.states.get(next_entity_id).state == STATE_UNKNOWN
    assert hass.states.get(last_event_entity_id).state == STATE_UNKNOWN
    assert hass.states.get(due_entity_id).state == STATE_OFF
    assert hass.states.get(overdue_entity_id).state == STATE_OFF
    assert hass.states.get(pending_binary_entity_id).state == STATE_OFF

    await _call_service(
        hass,
        "generate_tasks",
        {
            "slug": "pixel",
            "care_plan_id": plan["care_plan_id"],
            "now": datetime(2026, 8, 5, 12, tzinfo=UTC),
            "horizon_duration": {"days": 1},
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get(pending_entity_id).state == "1"
    assert hass.states.get(next_entity_id).state == "Feed Fruit Mix"
    assert hass.states.get(due_entity_id).state == STATE_OFF
    assert hass.states.get(overdue_entity_id).state == STATE_ON
    assert hass.states.get(pending_binary_entity_id).state == STATE_ON
    assert hass.states.get(pending_entity_id).attributes["task_ids"]
    assert hass.states.get(pending_entity_id).attributes["reptile_id"] == reptile_id
    assert hass.states.get(pending_entity_id).attributes["slug"] == "pixel"
    assert hass.states.get(next_entity_id).attributes["slug"] == "pixel"

    tasks = await _call_service(
        hass,
        "get_tasks",
        {
            "slug": "pixel",
            "care_plan_id": plan["care_plan_id"],
            "include_details": True,
        },
    )
    task_id = tasks["tasks"][0]["task_id"]
    assert tasks["tasks"][0]["presentation"]["title"] == "Feed Fruit Mix"
    assert tasks["tasks"][0]["presentation"]["icon"] == "mdi:food-apple"
    assert tasks["tasks"][0]["completion_schema"]["outcomes"][0]["outcome_id"]

    await _call_service(
        hass,
        "resolve_task",
        {
            "task_id": task_id,
            "action": "complete",
            "outcome_id": "ate_normally",
            "completed_at": datetime(2026, 8, 5, 12, tzinfo=UTC),
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get(last_event_entity_id).state == "Feeding"
    assert hass.states.get(pending_entity_id).state == "1"
    assert hass.states.get(next_entity_id).state == "Remove Food"
    assert hass.states.get(due_entity_id).state == STATE_OFF
    assert hass.states.get(pending_binary_entity_id).state == STATE_ON

    await _call_service(
        hass,
        "log_event",
        {
            "slug": "pixel",
            "event_type": "health_note",
            "timestamp": datetime(2026, 8, 5, 13, tzinfo=UTC),
            "context": {"observation": "Alert"},
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get(last_event_entity_id).state == "Health Note"

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {"entity_id": button_entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert int(hass.states.get(pending_entity_id).state) >= 1


async def test_dynamic_entity_creation_and_disabled_reptile_behavior(
    hass: HomeAssistant,
) -> None:
    """New reptiles appear dynamically and disabled reptiles become unavailable."""
    await _setup_entry(hass)
    entity_registry = er.async_get(hass)

    assert not any(
        entry.platform == "sensor" and entry.unique_id.endswith("_pending_task_count")
        for entry in entity_registry.entities.values()
    )

    pixel = await _create_pixel(hass)
    reptile_id = pixel["reptile_id"]
    await hass.async_block_till_done()

    pending_entity_id = _entity_id(
        entity_registry, "sensor", f"{reptile_id}_pending_task_count"
    )
    assert hass.states.get(pending_entity_id).state == "0"

    await _call_service(hass, "disable_reptile", {"slug": "pixel"})
    await hass.async_block_till_done()
    assert hass.states.get(pending_entity_id).state == STATE_UNAVAILABLE

    await _call_service(hass, "enable_reptile", {"reptile_id": reptile_id})
    await hass.async_block_till_done()
    assert hass.states.get(pending_entity_id).state == "0"


async def test_generate_tasks_button_is_idempotent(
    hass: HomeAssistant,
) -> None:
    """The button delegates to generation and repeated presses stay idempotent."""
    await _setup_entry(hass)
    pixel = await _create_pixel(hass)
    reptile_id = pixel["reptile_id"]
    await _create_plan(hass)
    entity_registry = er.async_get(hass)

    pending_entity_id = _entity_id(
        entity_registry, "sensor", f"{reptile_id}_pending_task_count"
    )
    button_entity_id = _entity_id(
        entity_registry, "button", f"{reptile_id}_generate_tasks"
    )

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {"entity_id": button_entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    first_count = int(hass.states.get(pending_entity_id).state)
    assert first_count >= 1

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {"entity_id": button_entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    second_count = int(hass.states.get(pending_entity_id).state)
    assert second_count == first_count
