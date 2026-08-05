"""Binary sensor platform for compact per-reptile care status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ReptileCareConfigEntry
from .entity import ReptileCareEntity, async_setup_reptile_platform


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ReptileCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ReptileCare binary sensor entities."""
    async_setup_reptile_platform(entry, async_add_entities, _binary_entities)


def _binary_entities(
    entry: ReptileCareConfigEntry, reptile_id: str
) -> list[ReptileCareEntity]:
    return [
        ReptileCareDueBinarySensor(entry, reptile_id),
        ReptileOverdueCareBinarySensor(entry, reptile_id),
        ReptilePendingCareBinarySensor(entry, reptile_id),
    ]


class _ReptileCareBinarySensor(ReptileCareEntity, BinarySensorEntity):
    """Common compact attributes for reptile care binary sensors."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        projection = self._runtime.entity_projection.project_reptile(self._reptile_id)
        pending = projection.pending_tasks
        return {
            "pending_count": pending.pending_count,
            "due_count": pending.due_count,
            "overdue_count": pending.overdue_count,
            "upcoming_count": pending.upcoming_count,
            "snoozed_count": pending.snoozed_count,
            "next_due": None
            if pending.next_due is None
            else pending.next_due.isoformat(),
        }


class ReptileCareDueBinarySensor(_ReptileCareBinarySensor):
    """On when the reptile has at least one currently due task."""

    _attr_translation_key = "care_due"
    _attr_unique_id_suffix = "care_due"

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_{self._attr_unique_id_suffix}"

    @property
    def is_on(self) -> bool:
        return (
            self._runtime.entity_projection.project_reptile(
                self._reptile_id
            ).pending_tasks.due_count
            > 0
        )


class ReptileOverdueCareBinarySensor(_ReptileCareBinarySensor):
    """On when the reptile has at least one overdue task."""

    _attr_translation_key = "overdue_care"
    _attr_unique_id_suffix = "overdue_care"

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_{self._attr_unique_id_suffix}"

    @property
    def is_on(self) -> bool:
        return (
            self._runtime.entity_projection.project_reptile(
                self._reptile_id
            ).pending_tasks.overdue_count
            > 0
        )


class ReptilePendingCareBinarySensor(_ReptileCareBinarySensor):
    """On when the reptile has any pending care task."""

    _attr_translation_key = "pending_care"
    _attr_unique_id_suffix = "pending_care"

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_{self._attr_unique_id_suffix}"

    @property
    def is_on(self) -> bool:
        return (
            self._runtime.entity_projection.project_reptile(
                self._reptile_id
            ).pending_tasks.pending_count
            > 0
        )
