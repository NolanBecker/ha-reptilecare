"""The LizardCare integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import LizardCareCoordinator
from .storage import NullEventStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: tuple[Platform, ...] = ()


async def async_setup_entry(hass: HomeAssistant, entry: LizardCareConfigEntry) -> bool:
    """Set up LizardCare from a config entry."""
    store = NullEventStore()
    coordinator = LizardCareCoordinator(
        hass=hass,
        config_entry=entry,
        event_store=store,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = LizardCareRuntimeData(
        coordinator=coordinator,
        event_store=store,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("LizardCare initialized")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LizardCareConfigEntry) -> bool:
    """Unload a LizardCare config entry."""
    unload_ok = not PLATFORMS or await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        _LOGGER.info("LizardCare unloaded")
    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant, entry: LizardCareConfigEntry
) -> None:
    """Reload LizardCare when its config entry is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


from .models import LizardCareRuntimeData  # noqa: E402

type LizardCareConfigEntry = ConfigEntry[LizardCareRuntimeData]
