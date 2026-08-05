"""Tests for ReptileCare diagnostics."""

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
