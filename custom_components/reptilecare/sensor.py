"""Sensor platform for compact per-reptile care projections."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ReptileCareConfigEntry
from .entity import ReptileCareEntity, async_setup_reptile_platform


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ReptileCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ReptileCare sensor entities."""
    async_setup_reptile_platform(entry, async_add_entities, _sensor_entities)


def _sensor_entities(
    entry: ReptileCareConfigEntry, reptile_id: str
) -> list[ReptileCareEntity]:
    return [
        ReptilePendingTasksSensor(entry, reptile_id),
        ReptileNextTaskSensor(entry, reptile_id),
        ReptileLastEventSensor(entry, reptile_id),
    ]


class ReptilePendingTasksSensor(ReptileCareEntity, SensorEntity):
    """Expose the compact pending-task count for one reptile."""

    _attr_translation_key = "pending_tasks"
    _attr_unique_id_suffix = "pending_task_count"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> int:
        return self._runtime.entity_projection.project_reptile(
            self._reptile_id
        ).pending_tasks.pending_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        projection = self._runtime.entity_projection.project_reptile(self._reptile_id)
        pending = projection.pending_tasks
        return {
            "next_due": None
            if pending.next_due is None
            else pending.next_due.isoformat(),
            "due_count": pending.due_count,
            "overdue_count": pending.overdue_count,
            "upcoming_count": pending.upcoming_count,
            "snoozed_count": pending.snoozed_count,
            "task_ids": list(pending.task_ids),
        }


class ReptileNextTaskSensor(ReptileCareEntity, SensorEntity):
    """Expose the next actionable task for one reptile."""

    _attr_translation_key = "next_task"
    _attr_unique_id_suffix = "next_task"

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> str | None:
        next_task = self._runtime.entity_projection.project_reptile(
            self._reptile_id
        ).next_task
        return None if next_task is None else next_task.display_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        next_task = self._runtime.entity_projection.project_reptile(
            self._reptile_id
        ).next_task
        if next_task is None:
            return {}
        return {
            "task_id": next_task.task_id,
            "task_template_id": next_task.task_template_id,
            "care_plan_id": next_task.care_plan_id,
            "due_at": next_task.due_at.isoformat(),
            "timing_state": next_task.timing_state.value,
            "priority": next_task.priority.value,
            "generation_reason": next_task.generation_reason,
        }


class ReptileLastEventSensor(ReptileCareEntity, SensorEntity):
    """Expose the latest event summary for one reptile."""

    _attr_translation_key = "last_event"
    _attr_unique_id_suffix = "last_event"

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> str | None:
        last_event = self._runtime.entity_projection.project_reptile(
            self._reptile_id
        ).last_event
        return None if last_event is None else last_event.label

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last_event = self._runtime.entity_projection.project_reptile(
            self._reptile_id
        ).last_event
        if last_event is None:
            return {}
        return {
            "event_id": last_event.event_id,
            "event_type": last_event.event_type,
            "timestamp": last_event.timestamp.isoformat(),
            "outcome_id": last_event.outcome_id,
            "task_id": last_event.task_id,
            "care_plan_id": last_event.care_plan_id,
            "source": last_event.source,
        }
