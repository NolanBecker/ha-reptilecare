"""Diagnostics support for ReptileCare."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import ReptileCareConfigEntry
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: ReptileCareConfigEntry
) -> dict[str, Any]:
    """Return safe diagnostics for a ReptileCare config entry."""
    return {
        "domain": DOMAIN,
        "config_entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "runtime": {
            "event_count": len(entry.runtime_data.coordinator.data.events),
            "reptile_count": len(entry.runtime_data.reptile_repository.all()),
            "event_storage": type(entry.runtime_data.event_store).__name__,
        },
    }
