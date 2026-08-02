"""Event-driven data coordination for LizardCare."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import INTEGRATION_NAME
from .models import LizardCareSnapshot
from .storage import EventStore

_LOGGER = logging.getLogger(__name__)


class LizardCareCoordinator(DataUpdateCoordinator[LizardCareSnapshot]):
    """Coordinate LizardCare state without periodic polling.

    Future feature modules can call ``async_handle_event`` after committing an
    event to the configured store. The coordinator then publishes a new
    immutable snapshot to all subscribed entities.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        event_store: EventStore,
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

    async def _async_update_data(self) -> LizardCareSnapshot:
        """Build the initial snapshot from the configured event store."""
        events = await self.event_store.async_list_events()
        return LizardCareSnapshot(events=events)

    @callback
    def async_handle_event(self, snapshot: LizardCareSnapshot) -> None:
        """Publish state produced by an event-driven feature module."""
        self.async_set_updated_data(snapshot)
