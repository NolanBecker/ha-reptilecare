"""Shared data models for LizardCare."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coordinator import LizardCareCoordinator
    from .storage import EventStore


@dataclass(frozen=True, slots=True)
class LizardCareEvent:
    """An immutable event belonging to one reptile.

    ``event_type`` is intentionally open-ended so feeding, cleaning, weight,
    shedding, health, notes, photos, and environment modules can define their
    own event vocabulary without changing the storage contract.
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
