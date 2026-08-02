"""The ReptileCare integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ReptileCareCoordinator
from .storage import HomeAssistantCareEventStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: tuple[Platform, ...] = ()


async def async_setup_entry(hass: HomeAssistant, entry: ReptileCareConfigEntry) -> bool:
    """Set up ReptileCare from a config entry."""
    store = HomeAssistantCareEventStore(hass, entry.entry_id)
    await store.async_load()
    coordinator = ReptileCareCoordinator(
        hass=hass,
        config_entry=entry,
        event_store=store,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ReptileCareRuntimeData(
        coordinator=coordinator,
        event_store=store,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("ReptileCare initialized")
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ReptileCareConfigEntry
) -> bool:
    """Unload a ReptileCare config entry."""
    unload_ok = not PLATFORMS or await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        _LOGGER.info("ReptileCare unloaded")
    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant, entry: ReptileCareConfigEntry
) -> None:
    """Reload ReptileCare when its config entry is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


from .models import ReptileCareRuntimeData  # noqa: E402

type ReptileCareConfigEntry = ConfigEntry[ReptileCareRuntimeData]
