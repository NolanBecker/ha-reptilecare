"""Base entities for future LizardCare platforms."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LizardCareCoordinator


class LizardCareEntity(CoordinatorEntity[LizardCareCoordinator]):
    """Base class for future LizardCare entities."""

    _attr_has_entity_name = True
