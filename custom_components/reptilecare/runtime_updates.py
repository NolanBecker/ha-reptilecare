"""Dispatcher helpers for runtime-driven entity updates."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_RUNTIME_UPDATED


def async_notify_runtime_updated(hass: HomeAssistant) -> None:
    """Notify listeners that ReptileCare runtime state has changed."""
    async_dispatcher_send(hass, SIGNAL_RUNTIME_UPDATED)
