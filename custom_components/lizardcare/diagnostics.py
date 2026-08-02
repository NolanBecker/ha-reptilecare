"""Diagnostics support for LizardCare."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import LizardCareConfigEntry
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: LizardCareConfigEntry
) -> dict[str, Any]:
    """Return safe diagnostics for a LizardCare config entry."""
    return {
        "domain": DOMAIN,
        "config_entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "runtime": {
            "event_count": len(entry.runtime_data.coordinator.data.events),
            "storage": type(entry.runtime_data.event_store).__name__,
        },
    }
