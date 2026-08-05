"""Base entities for future ReptileCare platforms."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ReptileCareConfigEntry
from .const import DOMAIN, MANUFACTURER, SIGNAL_RUNTIME_UPDATED
from .coordinator import ReptileCareCoordinator
from .domain.reptile import Reptile

_LOGGER = logging.getLogger(__name__)


class ReptileCareEntity(CoordinatorEntity[ReptileCareCoordinator]):
    """Base class for future ReptileCare entities."""

    _attr_has_entity_name = True

    def __init__(self, entry: ReptileCareConfigEntry, reptile_id: str) -> None:
        """Initialize a ReptileCare entity tied to one reptile."""
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._runtime = entry.runtime_data
        self._reptile_id = reptile_id

    @property
    def reptile(self) -> Reptile | None:
        """Return the current reptile record, if it still exists."""
        try:
            return self._runtime.reptile_repository.get(self._reptile_id)
        except Exception:
            return None

    @property
    def available(self) -> bool:
        """Keep entities available unless runtime or reptile identity is missing."""
        reptile = self.reptile
        return super().available and reptile is not None and reptile.enabled

    @property
    def device_info(self) -> DeviceInfo:
        """Attach all reptile entities to one stable reptile device."""
        reptile = self.reptile
        model = None
        if reptile is not None:
            model = self._runtime.entity_projection.species_model(reptile.reptile_id)
        return DeviceInfo(
            identifiers={(DOMAIN, self._reptile_id)},
            manufacturer=MANUFACTURER,
            name=self._reptile_name,
            model=model,
        )

    @property
    def _reptile_name(self) -> str:
        reptile = self.reptile
        return self._reptile_id if reptile is None else reptile.display_name

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime change notifications."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RUNTIME_UPDATED,
                self._handle_runtime_updated,
            )
        )

    def _handle_runtime_updated(self) -> None:
        """Refresh entity state on repository-driven runtime updates."""
        self.async_write_ha_state()


def async_setup_reptile_platform(
    entry: ReptileCareConfigEntry,
    async_add_entities: Callable[[Iterable[ReptileCareEntity]], None],
    entity_factory: Callable[[ReptileCareConfigEntry, str], list[ReptileCareEntity]],
) -> None:
    """Add reptile entities now and on future runtime discovery updates."""
    known_ids: set[str] = set()

    def _add_missing() -> None:
        new_entities: list[ReptileCareEntity] = []
        for reptile_id in entry.runtime_data.entity_projection.all_reptile_ids():
            if reptile_id in known_ids:
                continue
            known_ids.add(reptile_id)
            new_entities.extend(entity_factory(entry, reptile_id))
        if new_entities:
            _LOGGER.debug(
                "Adding %s ReptileCare entities for platform %s",
                len(new_entities),
                type(new_entities[0]).__name__,
            )
            async_add_entities(new_entities)

    _add_missing()
    entry.async_on_unload(
        async_dispatcher_connect(
            entry.runtime_data.coordinator.hass,
            SIGNAL_RUNTIME_UPDATED,
            _add_missing,
        )
    )
