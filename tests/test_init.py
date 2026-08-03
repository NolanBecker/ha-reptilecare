"""Tests for ReptileCare setup and lifecycle."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME
from custom_components.reptilecare.domain.reptile import Reptile
from custom_components.reptilecare.models import (
    CareEvent,
    CareEventType,
    ReptileCareRuntimeData,
    ReptileCareSnapshot,
)

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading ReptileCare."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, ReptileCareRuntimeData)
    assert entry.runtime_data.coordinator.data.events == ()
    assert entry.runtime_data.coordinator.timeline.all_events() == ()
    assert entry.runtime_data.timeline.all_events() == ()
    assert entry.runtime_data.species_profiles.contains("builtin:gargoyle_gecko")
    assert entry.runtime_data.task_templates.contains("builtin:feed_fruit")
    assert entry.runtime_data.reptile_repository.all() == ()

    event = CareEvent(reptile_id=PIXEL_ID, event_type=CareEventType.FEEDING)
    snapshot = ReptileCareSnapshot(events=(event,))
    entry.runtime_data.coordinator.async_handle_event(snapshot)
    assert entry.runtime_data.coordinator.timeline.latest_event() is event

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_reload_rebuilds_species_registry(hass: HomeAssistant) -> None:
    """Reloading reconstructs and exposes the built-in profile registry."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    original_registry = entry.runtime_data.species_profiles
    original_repository = entry.runtime_data.reptile_repository
    original_templates = entry.runtime_data.task_templates
    pixel = Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )
    await original_repository.async_add(pixel)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.species_profiles is not original_registry
    assert entry.runtime_data.reptile_repository is not original_repository
    assert entry.runtime_data.task_templates is not original_templates
    assert entry.runtime_data.reptile_repository.get(PIXEL_ID) == pixel
    assert entry.runtime_data.species_profiles.contains("builtin:gargoyle_gecko")
    assert entry.runtime_data.task_templates.contains("builtin:feed_fruit")


async def test_invalid_builtin_profile_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid bundled profile data fails setup with a clear config-entry error."""
    from custom_components.reptilecare import (
        SpeciesProfileRegistry,
        async_setup_entry,
    )
    from custom_components.reptilecare.domain.species import InvalidSpeciesProfileError

    def _raise_invalid_profile() -> None:
        raise InvalidSpeciesProfileError("invalid packaged profile")

    monkeypatch.setattr(
        SpeciesProfileRegistry, "load_builtin_profiles", _raise_invalid_profile
    )
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="built-in species profiles"):
        await async_setup_entry(hass, entry)


async def test_invalid_builtin_task_template_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid bundled task template data fails setup clearly."""
    from custom_components.reptilecare import TaskTemplateRegistry, async_setup_entry
    from custom_components.reptilecare.domain.task_template import (
        InvalidTaskTemplateError,
    )

    def _raise_invalid_template() -> None:
        raise InvalidTaskTemplateError("invalid packaged task template")

    monkeypatch.setattr(
        TaskTemplateRegistry, "load_builtin_templates", _raise_invalid_template
    )
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="built-in task templates"):
        await async_setup_entry(hass, entry)
