"""Shared data models for LizardCare."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coordinator import LizardCareCoordinator
    from .storage import EventStore


class EventType(StrEnum):
    """Canonical event types supported by future LizardCare milestones."""

    FEEDING = "feeding"
    FOOD_REMOVED = "food_removed"
    SPOT_CLEAN = "spot_clean"
    DEEP_CLEAN = "deep_clean"
    WEIGHT = "weight"
    SHED = "shed"
    HEALTH_NOTE = "health_note"
    PHOTO = "photo"


@dataclass(frozen=True, slots=True)
class LizardCareEvent:
    """An immutable event belonging to one reptile.

    The event type remains serialized as a string in the foundation model.
    Future event producers should use ``EventType`` as their canonical
    vocabulary without changing the storage contract.
    """

    event_id: str
    reptile_id: str
    event_type: str
    occurred_at: datetime
    data: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class LizardCareSnapshot:
    """Current coordinator state derived from the event stream."""

    events: tuple[LizardCareEvent, ...] = ()


@dataclass(slots=True)
class LizardCareRuntimeData:
    """Runtime dependencies owned by a config entry."""

    coordinator: LizardCareCoordinator
    event_store: EventStore
