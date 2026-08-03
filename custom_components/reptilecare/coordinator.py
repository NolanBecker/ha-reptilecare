"""Event-driven data coordination for ReptileCare."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import INTEGRATION_NAME
from .models import ReptileCareSnapshot
from .storage import CareEventStore
from .timeline import Timeline

_LOGGER = logging.getLogger(__name__)


class ReptileCareCoordinator(DataUpdateCoordinator[ReptileCareSnapshot]):
    """Coordinate ReptileCare state without periodic polling.

    Future feature modules can call ``async_handle_event`` after committing an
    event to the configured store. The coordinator then publishes a new
    immutable snapshot to all subscribed entities.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        event_store: CareEventStore,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=config_entry,
            name=INTEGRATION_NAME,
            update_interval=None,
        )
        self.event_store = event_store
        self.timeline = Timeline()

    async def _async_update_data(self) -> ReptileCareSnapshot:
        """Build the initial snapshot from the configured event store."""
        events = await self.event_store.async_list_events()
        self.timeline = Timeline(events)
        return ReptileCareSnapshot(events=events)

    @callback
    def async_handle_event(self, snapshot: ReptileCareSnapshot) -> None:
        """Publish state produced by an event-driven feature module."""
        self.timeline = Timeline(snapshot.events)
        self.async_set_updated_data(snapshot)
