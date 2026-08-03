"""Shared domain models for ReptileCare."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from .coordinator import ReptileCareCoordinator
    from .domain.reptile import ReptileRepository
    from .domain.species import SpeciesProfileRegistry
    from .domain.task_template import TaskTemplateRegistry
    from .domain.workflow import WorkflowRegistry
    from .storage import CareEventStore
    from .timeline import Timeline


class CareEventType(StrEnum):
    """Canonical event types supported by ReptileCare."""

    FEEDING = "feeding"
    FOOD_REMOVED = "food_removed"
    SPOT_CLEAN = "spot_clean"
    DEEP_CLEAN = "deep_clean"
    WEIGHT = "weight"
    SHED = "shed"
    HEALTH_NOTE = "health_note"
    PHOTO = "photo"


def _utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def _freeze_value(value: Any) -> Any:
    """Recursively copy mutable containers into immutable equivalents."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return deepcopy(value)


def _immutable_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy metadata so external mutations cannot change an event."""
    return MappingProxyType(
        {str(key): _freeze_value(value) for key, value in metadata.items()}
    )


@dataclass(frozen=True, slots=True)
class CareEvent:
    """An immutable event belonging to one reptile."""

    reptile_id: str
    event_type: CareEventType
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    event_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """Normalize and validate immutable event fields."""
        if not self.reptile_id.strip():
            raise ValueError("reptile_id must not be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

        object.__setattr__(self, "reptile_id", self.reptile_id.strip())
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ReptileCareSnapshot:
    """Lightweight coordinator state derived from the event stream."""

    events: tuple[CareEvent, ...] = ()


@dataclass(slots=True)
class ReptileCareRuntimeData:
    """Runtime dependencies owned by a config entry."""

    coordinator: ReptileCareCoordinator
    event_store: CareEventStore
    species_profiles: SpeciesProfileRegistry
    reptile_repository: ReptileRepository
    task_templates: TaskTemplateRegistry
    workflow_graphs: WorkflowRegistry

    @property
    def timeline(self) -> Timeline:
        """Expose the coordinator's current Timeline."""
        return self.coordinator.timeline
