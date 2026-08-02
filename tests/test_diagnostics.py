"""Tests for LizardCare diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lizardcare.const import DOMAIN, INTEGRATION_NAME
from custom_components.lizardcare.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics(hass: HomeAssistant) -> None:
    """Test diagnostics contain only scaffold metadata."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics == {
        "domain": DOMAIN,
        "config_entry": {"version": 1, "minor_version": 1},
        "runtime": {"event_count": 0, "storage": "HomeAssistantEventStore"},
    }
