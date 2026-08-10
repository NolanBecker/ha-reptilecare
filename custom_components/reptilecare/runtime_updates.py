"""Dispatcher helpers for runtime-driven entity updates."""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .application import CareEventRecorded, ReptileCareApplicationEvent
from .const import SIGNAL_RUNTIME_EVENT, SIGNAL_RUNTIME_UPDATED
from .coordinator import ReptileCareCoordinator
from .models import ReptileCareSnapshot
from .storage import CareEventStore


def async_notify_runtime_updated(hass: HomeAssistant | None) -> None:
    """Notify listeners that ReptileCare runtime state has changed."""
    if hass is None:
        return
    async_dispatcher_send(hass, SIGNAL_RUNTIME_UPDATED)


class HomeAssistantRuntimeEventPublisher:
    """Translate application events into Home Assistant runtime updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ReptileCareCoordinator,
        event_store: CareEventStore,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._event_store = event_store

    async def async_publish(self, event: ReptileCareApplicationEvent) -> None:
        """Publish one event."""
        await self.async_publish_many((event,))

    async def async_publish_many(
        self,
        events: tuple[ReptileCareApplicationEvent, ...],
    ) -> None:
        """Publish multiple events while refreshing coordinator state once."""
        if not events:
            return

        if any(isinstance(event, CareEventRecorded) for event in events):
            snapshot = ReptileCareSnapshot(
                events=await self._event_store.async_list_events()
            )
            self._coordinator.async_handle_event(snapshot)

        for event in events:
            async_dispatcher_send(
                self._hass,
                SIGNAL_RUNTIME_EVENT,
                {
                    "event_type": type(event).__name__,
                    "payload": asdict(event),
                },
            )

        async_notify_runtime_updated(self._hass)
