"""Pure projection helpers for ReptileCare entity state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from .domain.care_plan import CarePlanNotFoundError, CarePlanRepository
from .domain.care_task import (
    CareTask,
    CareTaskDueState,
    CareTaskRepository,
    CareTaskStatus,
    project_due_state,
)
from .domain.reptile import ReptileRepository
from .domain.species import SpeciesProfileRegistry
from .domain.task_template import (
    TaskPriority,
    TaskTemplateNotFoundError,
    TaskTemplateRegistry,
)
from .models import CareEventType
from .timeline import Timeline

_PENDING_TASK_ID_LIMIT = 5
_EVENT_LABELS = {
    CareEventType.FEEDING: "Feeding",
    CareEventType.FOOD_REMOVED: "Food Removed",
    CareEventType.SPOT_CLEAN: "Spot Clean",
    CareEventType.DEEP_CLEAN: "Deep Clean",
    CareEventType.WEIGHT: "Weight",
    CareEventType.SHED: "Shed",
    CareEventType.HEALTH_NOTE: "Health Note",
    CareEventType.PHOTO: "Photo",
}
_PRIORITY_RANK = {
    TaskPriority.URGENT: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}


@dataclass(frozen=True, slots=True)
class PendingTaskProjection:
    """Compact bounded pending-task summary for one reptile."""

    pending_count: int
    due_count: int
    overdue_count: int
    upcoming_count: int
    snoozed_count: int
    next_due: datetime | None
    task_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NextTaskProjection:
    """Compact summary of the next actionable CareTask."""

    task_id: str
    display_name: str
    task_template_id: str
    care_plan_id: str
    due_at: datetime
    timing_state: CareTaskDueState
    priority: TaskPriority
    generation_reason: str


@dataclass(frozen=True, slots=True)
class LastEventProjection:
    """Compact summary of the latest CareEvent."""

    event_id: str
    label: str
    event_type: str
    timestamp: datetime
    outcome_id: str | None
    task_id: str | None
    care_plan_id: str | None
    source: str | None


@dataclass(frozen=True, slots=True)
class ReptileEntityProjection:
    """Entity-facing compact projection for one reptile."""

    pending_tasks: PendingTaskProjection
    next_task: NextTaskProjection | None
    last_event: LastEventProjection | None
    care_state: str
    warnings: tuple[str, ...] = ()


class ReptileCareEntityProjection:
    """Pure projection layer for compact reptile dashboard state."""

    def __init__(
        self,
        reptile_repository: ReptileRepository,
        care_plan_repository: CarePlanRepository,
        care_task_repository: CareTaskRepository,
        task_templates: TaskTemplateRegistry,
        species_profiles: SpeciesProfileRegistry,
        timeline_getter: Callable[[], Timeline],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the projection layer with existing runtime state."""
        self._reptile_repository = reptile_repository
        self._care_plan_repository = care_plan_repository
        self._care_task_repository = care_task_repository
        self._task_templates = task_templates
        self._species_profiles = species_profiles
        self._timeline_getter = timeline_getter
        self._now_provider = (
            now_provider if now_provider is not None else lambda: datetime.now(UTC)
        )

    def all_reptile_ids(self, *, include_disabled: bool = True) -> tuple[str, ...]:
        """Return reptile identifiers in stable repository order."""
        return tuple(
            reptile.reptile_id
            for reptile in self._reptile_repository.all(
                include_disabled=include_disabled
            )
        )

    def project_reptile(self, reptile_id: str) -> ReptileEntityProjection:
        """Project compact entity-facing state for one reptile."""
        now = self._now_provider().astimezone(UTC)
        warnings: list[str] = []
        pending_tasks = tuple(
            task
            for task in self._care_task_repository.for_reptile(reptile_id)
            if task.status is CareTaskStatus.PENDING
        )
        pending_projection = self._project_pending_tasks(pending_tasks, now=now)
        next_task = self._select_next_task(pending_tasks, now=now, warnings=warnings)
        last_event = self._latest_event(reptile_id)
        return ReptileEntityProjection(
            pending_tasks=pending_projection,
            next_task=next_task,
            last_event=last_event,
            care_state=self._care_state(pending_projection),
            warnings=tuple(warnings),
        )

    def species_model(self, reptile_id: str) -> str | None:
        """Return the species display name used as the device model."""
        reptile = self._reptile_repository.get(reptile_id)
        try:
            return self._species_profiles.get(reptile.species_profile_id).display_name
        except Exception:
            return None

    def _project_pending_tasks(
        self,
        tasks: tuple[CareTask, ...],
        *,
        now: datetime,
    ) -> PendingTaskProjection:
        due_count = 0
        overdue_count = 0
        upcoming_count = 0
        snoozed_count = 0
        ordered = tuple(sorted(tasks, key=lambda task: (task.due_at, task.task_id)))
        for task in ordered:
            state = project_due_state(task, now=now)
            if state is CareTaskDueState.DUE:
                due_count += 1
            elif state is CareTaskDueState.OVERDUE:
                overdue_count += 1
            elif state is CareTaskDueState.UPCOMING:
                upcoming_count += 1
            elif state is CareTaskDueState.SNOOZED:
                snoozed_count += 1
        next_task = self._select_next_task(ordered, now=now, warnings=[])
        return PendingTaskProjection(
            pending_count=len(ordered),
            due_count=due_count,
            overdue_count=overdue_count,
            upcoming_count=upcoming_count,
            snoozed_count=snoozed_count,
            next_due=None if next_task is None else next_task.due_at,
            task_ids=tuple(task.task_id for task in ordered[:_PENDING_TASK_ID_LIMIT]),
        )

    def _select_next_task(
        self,
        tasks: tuple[CareTask, ...],
        *,
        now: datetime,
        warnings: list[str],
    ) -> NextTaskProjection | None:
        actionable: list[tuple[datetime, int, str, CareTaskDueState, CareTask]] = []
        for task in tasks:
            state = project_due_state(task, now=now)
            if state is CareTaskDueState.SNOOZED:
                continue
            priority = self._task_priority(task, warnings)
            actionable.append(
                (
                    task.due_at,
                    _PRIORITY_RANK[priority],
                    task.task_id,
                    state,
                    task,
                )
            )
        if not actionable:
            return None
        _, _, _, state, task = min(actionable)
        return NextTaskProjection(
            task_id=task.task_id,
            display_name=self._task_display_name(task, warnings),
            task_template_id=task.task_template_id,
            care_plan_id=task.care_plan_id,
            due_at=task.due_at,
            timing_state=state,
            priority=self._task_priority(task, warnings),
            generation_reason=task.generation_reason.value,
        )

    def _latest_event(self, reptile_id: str) -> LastEventProjection | None:
        events = self._timeline_getter().events_for_reptile(reptile_id)
        if not events:
            return None
        event = events[-1]
        return LastEventProjection(
            event_id=str(event.event_id),
            label=_EVENT_LABELS[event.event_type],
            event_type=event.event_type.value,
            timestamp=event.timestamp,
            outcome_id=event.outcome_id,
            task_id=event.task_id,
            care_plan_id=event.care_plan_id,
            source=event.source,
        )

    def _task_display_name(self, task: CareTask, warnings: list[str]) -> str:
        try:
            return self._task_templates.get(task.task_template_id).display_name
        except TaskTemplateNotFoundError:
            warnings.append(
                "missing task template for task "
                f"{task.task_id}: {task.task_template_id}"
            )
        try:
            return self._care_plan_repository.get(task.care_plan_id).display_name
        except CarePlanNotFoundError:
            warnings.append(
                f"missing care plan for task {task.task_id}: {task.care_plan_id}"
            )
        return task.task_template_id

    def _task_priority(self, task: CareTask, warnings: list[str]) -> TaskPriority:
        try:
            return self._care_plan_repository.get(task.care_plan_id).priority
        except CarePlanNotFoundError:
            warnings.append(
                f"missing care plan for task {task.task_id}: {task.care_plan_id}"
            )
        try:
            return self._task_templates.get(task.task_template_id).default_priority
        except TaskTemplateNotFoundError:
            warnings.append(
                "missing task template for task "
                f"{task.task_id}: {task.task_template_id}"
            )
        return TaskPriority.NORMAL

    @staticmethod
    def _care_state(pending_tasks: PendingTaskProjection) -> str:
        if pending_tasks.overdue_count:
            return "overdue"
        if pending_tasks.due_count:
            return "due"
        if pending_tasks.pending_count:
            return "upcoming"
        return "clear"
