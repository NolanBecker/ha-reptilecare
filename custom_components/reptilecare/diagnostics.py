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
    reptile_ids = entry.runtime_data.entity_projection.all_reptile_ids()
    pending_counts: dict[str, int] = {}
    overdue_counts: dict[str, int] = {}
    projection_warnings: dict[str, list[str]] = {}
    for reptile_id in reptile_ids:
        projection = entry.runtime_data.entity_projection.project_reptile(reptile_id)
        pending_counts[reptile_id] = projection.pending_tasks.pending_count
        overdue_counts[reptile_id] = projection.pending_tasks.overdue_count
        if projection.warnings:
            projection_warnings[reptile_id] = list(projection.warnings)
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
            "entity_projection": {
                "entity_count_by_platform": {
                    "sensor": len(reptile_ids) * 3,
                    "binary_sensor": len(reptile_ids) * 3,
                    "button": len(reptile_ids),
                },
                "pending_task_counts": pending_counts,
                "overdue_task_counts": overdue_counts,
                "projection_warnings": projection_warnings,
            },
        },
    }
