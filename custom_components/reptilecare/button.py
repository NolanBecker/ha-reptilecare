"""Button platform for per-reptile care actions."""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ReptileCareConfigEntry
from .entity import ReptileCareEntity, async_setup_reptile_platform
from .runtime_updates import async_notify_runtime_updated

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ReptileCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ReptileCare button entities."""
    async_setup_reptile_platform(entry, async_add_entities, _button_entities)


def _button_entities(
    entry: ReptileCareConfigEntry, reptile_id: str
) -> list[ReptileCareEntity]:
    return [ReptileGenerateTasksButton(entry, reptile_id)]


class ReptileGenerateTasksButton(ReptileCareEntity, ButtonEntity):
    """Generate missing tasks for one reptile."""

    _attr_translation_key = "generate_tasks"

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        super().__init__(entry, reptile_id)
        self._attr_unique_id = f"{reptile_id}_generate_tasks"

    async def async_press(self) -> None:
        """Generate missing tasks with the production default horizon."""
        result = await self._runtime.care_task_generator.async_generate(
            now=datetime.now(UTC),
            reptile_id=self._reptile_id,
        )
        async_notify_runtime_updated(self.hass)
        if result.errors and not (
            result.created_task_ids
            or result.existing_task_ids
            or result.skipped_plan_ids
        ):
            message = "; ".join(
                f"{care_plan_id}: {detail}"
                for care_plan_id, detail in result.errors.items()
            )
            _LOGGER.error(
                "Generate tasks button failed for reptile %s: %s",
                self._reptile_id,
                message,
            )
            raise HomeAssistantError(message)
        if result.errors:
            _LOGGER.warning(
                "Generate tasks button for reptile %s completed with warnings: %s",
                self._reptile_id,
                dict(result.errors),
            )
        _LOGGER.info(
            "Generated tasks for reptile %s: created=%s existing=%s skipped=%s",
            self._reptile_id,
            len(result.created_task_ids),
            len(result.existing_task_ids),
            len(result.skipped_plan_ids),
        )
