"""Tests for LizardCare setup and lifecycle."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lizardcare.const import DOMAIN, INTEGRATION_NAME
from custom_components.lizardcare.models import (
    EventType,
    LizardCareEvent,
    LizardCareRuntimeData,
    LizardCareSnapshot,
)


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading LizardCare."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, LizardCareRuntimeData)
    assert entry.runtime_data.coordinator.data.events == ()
    assert entry.runtime_data.coordinator.timeline.all_events() == ()

    event = LizardCareEvent(reptile_id="pixel", event_type=EventType.FEEDING)
    snapshot = LizardCareSnapshot(events=(event,))
    entry.runtime_data.coordinator.async_handle_event(snapshot)
    assert entry.runtime_data.coordinator.timeline.latest_event() is event

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
