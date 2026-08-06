"""Application-level events published after persisted state changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CareTaskCreated:
    """A new care task was persisted."""

    reptile_id: str
    task_id: str
    care_plan_id: str
    task_template_id: str


@dataclass(frozen=True, slots=True)
class CareTaskResolved:
    """A care task reached a terminal state."""

    reptile_id: str
    task_id: str
    care_plan_id: str
    event_id: str


@dataclass(frozen=True, slots=True)
class CareEventRecorded:
    """A care event was appended to the immutable event store."""

    reptile_id: str
    event_id: str
    event_type: str
    task_id: str | None = None
    care_plan_id: str | None = None


@dataclass(frozen=True, slots=True)
class CarePlanUpdated:
    """A care plan changed and dependent projections should refresh."""

    reptile_id: str
    care_plan_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class ReptileUpdated:
    """A reptile changed and dependent projections should refresh."""

    reptile_id: str
    enabled: bool
    slug: str | None = None


type ReptileCareApplicationEvent = (
    CareEventRecorded
    | CarePlanUpdated
    | CareTaskCreated
    | CareTaskResolved
    | ReptileUpdated
)


class ReptileCareEventPublisher(Protocol):
    """Publishes application events to an outer adapter layer."""

    async def async_publish(self, event: ReptileCareApplicationEvent) -> None:
        """Publish one immutable application event."""

    async def async_publish_many(
        self,
        events: tuple[ReptileCareApplicationEvent, ...],
    ) -> None:
        """Publish multiple immutable application events."""
