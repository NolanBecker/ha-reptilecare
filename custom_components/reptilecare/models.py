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
    from .application.care_engine import CareEngine, WorkflowEvaluator
    from .coordinator import ReptileCareCoordinator
    from .domain.care_plan import CarePlanRepository
    from .domain.care_task import CareTaskRepository
    from .domain.reptile import ReptileRepository
    from .domain.species import SpeciesProfileRegistry
    from .domain.task_template import TaskTemplateRegistry
    from .domain.workflow import WorkflowRegistry
    from .entity_projection import ReptileCareEntityProjection
    from .storage import CareEventStore
    from .task_generation import CareTaskGenerator, ScheduleCalculator
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
    task_id: str | None = None
    care_plan_id: str | None = None
    outcome_id: str | None = None
    context: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    actor_id: str | None = None
    source: str | None = None
    environmental_snapshot: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    attachment_references: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    event_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """Normalize and validate immutable event fields."""
        if not self.reptile_id.strip():
            raise ValueError("reptile_id must not be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        for name in ("task_id", "care_plan_id", "outcome_id", "actor_id", "source"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValueError(f"{name} must not be empty when provided")
        context = _freeze_value(self.context)
        if not isinstance(context, Mapping):
            raise ValueError("context must be an object")
        environmental_snapshot = _freeze_value(self.environmental_snapshot)
        if not isinstance(environmental_snapshot, Mapping):
            raise ValueError("environmental_snapshot must be an object")
        attachment_references = tuple(
            value.strip()
            for value in self.attachment_references
            if isinstance(value, str) and value.strip()
        )
        if len(attachment_references) != len(self.attachment_references):
            raise ValueError("attachment_references must contain non-empty strings")

        object.__setattr__(self, "reptile_id", self.reptile_id.strip())
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        object.__setattr__(
            self, "task_id", None if self.task_id is None else self.task_id.strip()
        )
        object.__setattr__(
            self,
            "care_plan_id",
            None if self.care_plan_id is None else self.care_plan_id.strip(),
        )
        object.__setattr__(
            self,
            "outcome_id",
            None if self.outcome_id is None else self.outcome_id.strip(),
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(
            self,
            "actor_id",
            None if self.actor_id is None else self.actor_id.strip(),
        )
        object.__setattr__(
            self,
            "source",
            None if self.source is None else self.source.strip(),
        )
        object.__setattr__(self, "environmental_snapshot", environmental_snapshot)
        object.__setattr__(self, "attachment_references", attachment_references)
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
    care_plan_repository: CarePlanRepository
    care_task_repository: CareTaskRepository
    schedule_calculator: ScheduleCalculator
    care_task_generator: CareTaskGenerator
    workflow_evaluator: WorkflowEvaluator
    care_engine: CareEngine
    entity_projection: ReptileCareEntityProjection

    @property
    def timeline(self) -> Timeline:
        """Expose the coordinator's current Timeline."""
        return self.coordinator.timeline
