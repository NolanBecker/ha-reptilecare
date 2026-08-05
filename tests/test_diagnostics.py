"""Tests for ReptileCare diagnostics."""

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME
from custom_components.reptilecare.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics(hass: HomeAssistant) -> None:
    """Diagnostics expose bounded runtime and projection metadata."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics == {
        "domain": DOMAIN,
        "config_entry": {"version": 1, "minor_version": 1},
        "runtime": {
            "event_count": 0,
            "reptile_count": 0,
            "event_storage": "HomeAssistantCareEventStore",
            "entity_projection": {
                "entity_count_by_platform": {
                    "sensor": 0,
                    "binary_sensor": 0,
                    "button": 0,
                },
                "pending_task_counts": {},
                "overdue_task_counts": {},
                "projection_warnings": {},
            },
        },
    }


async def test_diagnostics_include_projection_counts_and_warnings() -> None:
    """Diagnostics include bounded per-reptile projection warnings and counts."""
    entry = SimpleNamespace(
        version=1,
        minor_version=1,
        runtime_data=SimpleNamespace(
            entity_projection=SimpleNamespace(
                all_reptile_ids=lambda: ("pixel-id", "beans-id"),
                project_reptile=lambda reptile_id: SimpleNamespace(
                    pending_tasks=SimpleNamespace(
                        pending_count=2 if reptile_id == "pixel-id" else 0,
                        overdue_count=1 if reptile_id == "pixel-id" else 0,
                    ),
                    warnings=("missing template",) if reptile_id == "pixel-id" else (),
                ),
            ),
            coordinator=SimpleNamespace(
                data=SimpleNamespace(events=("evt-1", "evt-2"))
            ),
            reptile_repository=SimpleNamespace(all=lambda: ("pixel", "beans")),
            event_store=SimpleNamespace(),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(
        SimpleNamespace(),
        entry,
    )

    assert diagnostics["runtime"]["entity_projection"]["pending_task_counts"] == {
        "pixel-id": 2,
        "beans-id": 0,
    }
    assert diagnostics["runtime"]["entity_projection"]["overdue_task_counts"] == {
        "pixel-id": 1,
        "beans-id": 0,
    }
    assert diagnostics["runtime"]["entity_projection"]["projection_warnings"] == {
        "pixel-id": ["missing template"]
    }
