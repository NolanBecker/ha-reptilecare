"""Base entities for future ReptileCare platforms."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ReptileCareCoordinator


class ReptileCareEntity(CoordinatorEntity[ReptileCareCoordinator]):
    """Base class for future ReptileCare entities."""

    _attr_has_entity_name = True
