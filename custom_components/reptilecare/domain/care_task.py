"""Care task domain models, serialization, due-state projection, and repository."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import math
import re
from types import MappingProxyType
from typing import Any, Protocol
from uuid import UUID, uuid4

from .care_plan import CarePlanNotFoundError, CarePlanRepository
from .reptile import ReptileNotFoundError, ReptileRepository
from .task_outcome import (
    InvalidTaskOutcomeError,
    TaskOutcome,
    task_outcome_from_dict,
    task_outcome_to_dict,
)
from .task_template import TaskTemplateNotFoundError, TaskTemplateRegistry
from .workflow import WorkflowNotFoundError, WorkflowRegistry

CARE_TASK_SCHEMA_VERSION = 2
_LOCAL_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class CareTaskError(Exception):
    """Base exception for care task operations."""


class InvalidCareTaskError(CareTaskError, ValueError):
    """Raised when a CareTask definition is malformed or unsupported."""


class DuplicateCareTaskError(CareTaskError):
    """Raised when a task identifier is already registered."""


class DuplicateGenerationKeyError(CareTaskError):
    """Raised when a generation key already exists in the repository."""


class CareTaskNotFoundError(CareTaskError, LookupError):
    """Raised when a requested CareTask is not registered."""


class UnknownTaskReptileError(CareTaskError, LookupError):
    """Raised when a CareTask references an unknown reptile."""


class UnknownCarePlanReferenceError(CareTaskError, LookupError):
    """Raised when a CareTask references an unknown CarePlan."""


class UnknownTaskTemplateReferenceError(CareTaskError, LookupError):
    """Raised when a CareTask references an unknown TaskTemplate."""


class UnknownWorkflowReferenceError(CareTaskError, LookupError):
    """Raised when a CareTask references an unknown WorkflowGraph."""


class CareTaskStatus(StrEnum):
    """Durable lifecycle states for persisted CareTasks."""

    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class CareTaskResolutionAction(StrEnum):
    """Explicit terminal actions accepted by the CareEngine."""

    COMPLETE = "complete"
    SKIP = "skip"
    CANCEL = "cancel"


class CareTaskGenerationReason(StrEnum):
    """Explain why a persisted CareTask exists."""

    RECURRING_CARE_PLAN = "recurring_care_plan"
    MANUAL = "manual"
    FOLLOW_UP = "follow_up"
    IMPORTED = "imported"
    SYSTEM_RECONCILIATION = "system_reconciliation"


class CareTaskDueState(StrEnum):
    """Derived non-persisted projection for pending CareTasks."""

    UPCOMING = "upcoming"
    DUE = "due"
    OVERDUE = "overdue"
    SNOOZED = "snoozed"
    TERMINAL = "terminal"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidCareTaskError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _aware_utc_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidCareTaskError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidCareTaskError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _optional_aware_utc_datetime(value: object, name: str) -> datetime | None:
    return None if value is None else _aware_utc_datetime(value, name)


def _deserialize_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise InvalidCareTaskError(f"{name} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise InvalidCareTaskError(f"{name} must be an ISO datetime") from err
    return _aware_utc_datetime(parsed, name)


def _deserialize_optional_datetime(value: object, name: str) -> datetime | None:
    if value is None:
        return None
    return _deserialize_datetime(value, name)


def _json_value(value: object, name: str) -> Any:
    """Recursively validate JSON-compatible metadata values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidCareTaskError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InvalidCareTaskError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise InvalidCareTaskError(f"{name} must contain only JSON-compatible values")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidCareTaskError(f"{name} must be an object")
    return value


def _keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    name: str,
) -> None:
    if missing := required - set(value):
        raise InvalidCareTaskError(
            f"{name} is missing keys: {', '.join(sorted(missing))}"
        )
    if unknown := set(value) - required - optional:
        raise InvalidCareTaskError(
            f"{name} contains unknown keys: {', '.join(sorted(unknown))}"
        )


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class CareTask:
    """A concrete persisted unit of work derived from keeper intent."""

    reptile_id: str
    care_plan_id: str
    task_template_id: str
    workflow_id: str
    due_at: datetime
    generation_key: str
    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: CareTaskStatus = CareTaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    outcome: TaskOutcome | None = None
    notes: str | None = None
    attachment_references: tuple[str, ...] = ()
    generated_by: str | None = None
    parent_task_id: str | None = None
    workflow_chain_id: str | None = None
    workflow_node_id: str | None = None
    snoozed_until: datetime | None = None
    assigned_user_id: str | None = None
    resolution_action: CareTaskResolutionAction | None = None
    resolution_actor_id: str | None = None
    resolution_source: str | None = None
    environmental_context: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    resolution_key: str | None = None
    resolution_reconciled_at: datetime | None = None
    generation_reason: CareTaskGenerationReason = (
        CareTaskGenerationReason.RECURRING_CARE_PLAN
    )
    schema_version: int = CARE_TASK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        task_id = _text(self.task_id, "task_id")
        try:
            UUID(task_id)
        except ValueError as err:
            raise InvalidCareTaskError("task_id must be a UUID") from err

        for name, value in (
            ("reptile_id", self.reptile_id),
            ("care_plan_id", self.care_plan_id),
        ):
            normalized = _text(value, name)
            try:
                UUID(normalized)
            except ValueError as err:
                raise InvalidCareTaskError(f"{name} must be a UUID") from err
            object.__setattr__(self, name, normalized)

        for name in ("task_template_id", "workflow_id", "generation_key"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

        try:
            status = CareTaskStatus(self.status)
        except (TypeError, ValueError) as err:
            raise InvalidCareTaskError("status is invalid") from err
        try:
            generation_reason = CareTaskGenerationReason(self.generation_reason)
        except (TypeError, ValueError) as err:
            raise InvalidCareTaskError("generation_reason is invalid") from err
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version < 1
        ):
            raise InvalidCareTaskError("schema_version must be a positive integer")

        created_at = _aware_utc_datetime(self.created_at, "created_at")
        due_at = _aware_utc_datetime(self.due_at, "due_at")
        completed_at = _optional_aware_utc_datetime(self.completed_at, "completed_at")
        snoozed_until = _optional_aware_utc_datetime(
            self.snoozed_until, "snoozed_until"
        )

        attachment_references = tuple(
            _text(value, "attachment_reference") for value in self.attachment_references
        )

        parent_task_id = _optional_text(self.parent_task_id, "parent_task_id")
        if parent_task_id is not None:
            try:
                UUID(parent_task_id)
            except ValueError as err:
                raise InvalidCareTaskError("parent_task_id must be a UUID") from err

        workflow_chain_id = _optional_text(self.workflow_chain_id, "workflow_chain_id")
        if workflow_chain_id is not None:
            try:
                UUID(workflow_chain_id)
            except ValueError as err:
                raise InvalidCareTaskError("workflow_chain_id must be a UUID") from err
        workflow_node_id = _optional_text(self.workflow_node_id, "workflow_node_id")
        if (
            workflow_node_id is not None
            and _LOCAL_ID.fullmatch(workflow_node_id) is None
        ):
            raise InvalidCareTaskError(
                "workflow_node_id must be a lowercase identifier"
            )

        resolution_action = None
        if self.resolution_action is not None:
            try:
                resolution_action = CareTaskResolutionAction(self.resolution_action)
            except (TypeError, ValueError) as err:
                raise InvalidCareTaskError("resolution_action is invalid") from err

        if self.outcome is None:
            outcome = None
        elif isinstance(self.outcome, TaskOutcome):
            outcome = self.outcome
        else:
            raise InvalidCareTaskError("outcome has an invalid type")

        environmental_context = _json_value(
            self.environmental_context, "environmental_context"
        )
        if not isinstance(environmental_context, Mapping):
            raise InvalidCareTaskError("environmental_context must be an object")
        resolution_key = _optional_text(self.resolution_key, "resolution_key")
        resolution_reconciled_at = _optional_aware_utc_datetime(
            self.resolution_reconciled_at,
            "resolution_reconciled_at",
        )

        if status is CareTaskStatus.PENDING:
            if completed_at is not None:
                raise InvalidCareTaskError(
                    "completed_at must be unset while task status is pending"
                )
            if resolution_action is not None:
                raise InvalidCareTaskError(
                    "resolution_action must be unset while task status is pending"
                )
            if resolution_key is not None:
                raise InvalidCareTaskError(
                    "resolution_key must be unset while task status is pending"
                )
            if resolution_reconciled_at is not None:
                raise InvalidCareTaskError(
                    "resolution_reconciled_at must be unset "
                    "while task status is pending"
                )
        else:
            if completed_at is None:
                raise InvalidCareTaskError(
                    "completed_at is required for terminal task statuses"
                )
            if resolution_reconciled_at is not None and resolution_key is None:
                raise InvalidCareTaskError(
                    "resolution_key is required when resolution_reconciled_at is set"
                )
            expected_action = {
                CareTaskStatus.COMPLETED: CareTaskResolutionAction.COMPLETE,
                CareTaskStatus.SKIPPED: CareTaskResolutionAction.SKIP,
                CareTaskStatus.CANCELLED: CareTaskResolutionAction.CANCEL,
            }[status]
            if (
                resolution_action is not None
                and resolution_action is not expected_action
            ):
                raise InvalidCareTaskError(
                    "resolution_action does not match task status"
                )

        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "generation_reason", generation_reason)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "due_at", due_at)
        object.__setattr__(self, "completed_at", completed_at)
        object.__setattr__(self, "snoozed_until", snoozed_until)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "notes", _optional_text(self.notes, "notes"))
        object.__setattr__(
            self, "generated_by", _optional_text(self.generated_by, "generated_by")
        )
        object.__setattr__(self, "parent_task_id", parent_task_id)
        object.__setattr__(self, "workflow_chain_id", workflow_chain_id)
        object.__setattr__(self, "workflow_node_id", workflow_node_id)
        object.__setattr__(
            self,
            "assigned_user_id",
            _optional_text(self.assigned_user_id, "assigned_user_id"),
        )
        object.__setattr__(self, "resolution_action", resolution_action)
        object.__setattr__(
            self,
            "resolution_actor_id",
            _optional_text(self.resolution_actor_id, "resolution_actor_id"),
        )
        object.__setattr__(
            self,
            "resolution_source",
            _optional_text(self.resolution_source, "resolution_source"),
        )
        object.__setattr__(self, "environmental_context", environmental_context)
        object.__setattr__(self, "resolution_key", resolution_key)
        object.__setattr__(
            self,
            "resolution_reconciled_at",
            resolution_reconciled_at,
        )
        object.__setattr__(self, "attachment_references", attachment_references)


def project_due_state(
    task: CareTask,
    *,
    now: datetime,
    overdue_grace: timedelta = timedelta(),
) -> CareTaskDueState:
    """Project a non-persisted due-state from durable task facts."""
    current_time = _aware_utc_datetime(now, "now")
    if overdue_grace < timedelta():
        raise InvalidCareTaskError("overdue_grace must not be negative")
    if task.status is not CareTaskStatus.PENDING:
        return CareTaskDueState.TERMINAL
    if task.snoozed_until is not None and task.snoozed_until > current_time:
        return CareTaskDueState.SNOOZED
    if current_time < task.due_at:
        return CareTaskDueState.UPCOMING
    if current_time <= task.due_at + overdue_grace:
        return CareTaskDueState.DUE
    return CareTaskDueState.OVERDUE


class CareTaskPersistence(Protocol):
    """Async persistence boundary used by CareTaskRepository."""

    async def async_load(self) -> tuple[CareTask, ...]:
        """Load persisted care tasks."""

    async def async_save(self, tasks: tuple[CareTask, ...]) -> None:
        """Persist the complete care task collection."""


class CareTaskRepository:
    """Validated async repository for persisted CareTasks."""

    def __init__(
        self,
        reptile_repository: ReptileRepository,
        care_plan_repository: CarePlanRepository,
        task_templates: TaskTemplateRegistry,
        workflow_graphs: WorkflowRegistry,
        persistence: CareTaskPersistence,
    ) -> None:
        """Initialize an unloaded repository."""
        self._reptile_repository = reptile_repository
        self._care_plan_repository = care_plan_repository
        self._task_templates = task_templates
        self._workflow_graphs = workflow_graphs
        self._persistence = persistence
        self._tasks: Mapping[str, CareTask] = MappingProxyType({})
        self._generation_keys: Mapping[str, str] = MappingProxyType({})
        self._write_lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load and validate all persisted tasks."""
        tasks = await self._persistence.async_load()
        self._publish(tasks)

    async def async_add(self, task: CareTask) -> None:
        """Add and persist a new task."""
        async with self._write_lock:
            if task.task_id in self._tasks:
                raise DuplicateCareTaskError(f"duplicate task ID: {task.task_id}")
            if task.generation_key in self._generation_keys:
                raise DuplicateGenerationKeyError(
                    f"duplicate generation_key: {task.generation_key}"
                )
            self._validate_references(task)
            await self._save((*self._tasks.values(), task))

    async def async_update(self, task: CareTask) -> None:
        """Replace and persist an existing task."""
        async with self._write_lock:
            if task.task_id not in self._tasks:
                raise CareTaskNotFoundError(f"task not found: {task.task_id}")
            existing = self._tasks[task.task_id]
            if (
                task.generation_key != existing.generation_key
                and task.generation_key in self._generation_keys
            ):
                raise DuplicateGenerationKeyError(
                    f"duplicate generation_key: {task.generation_key}"
                )
            self._validate_references(task)
            updated = dict(self._tasks)
            updated[task.task_id] = task
            await self._save(tuple(updated.values()))

    async def async_remove(self, task_id: str) -> CareTask:
        """Remove a task record from the repository."""
        async with self._write_lock:
            task = self.get(task_id)
            updated = dict(self._tasks)
            del updated[task.task_id]
            await self._save(tuple(updated.values()))
            return task

    async def async_enable(self, task_id: str) -> None:
        """Re-enable a cancelled task without changing its due time."""
        await self.async_update(
            replace(
                self.get(task_id),
                status=CareTaskStatus.PENDING,
                completed_at=None,
                outcome=None,
                resolution_action=None,
                resolution_actor_id=None,
                resolution_source=None,
                environmental_context=MappingProxyType({}),
                resolution_key=None,
                resolution_reconciled_at=None,
            )
        )

    async def async_disable(self, task_id: str) -> None:
        """Cancel an existing task while preserving its identity."""
        task = self.get(task_id)
        await self.async_update(
            replace(
                task,
                status=CareTaskStatus.CANCELLED,
                completed_at=datetime.now(UTC),
                outcome=None,
                resolution_action=CareTaskResolutionAction.CANCEL,
                resolution_source="repository_disable",
            )
        )

    def get(self, task_id: str) -> CareTask:
        """Return one task by permanent identifier."""
        try:
            return self._tasks[task_id]
        except KeyError as err:
            raise CareTaskNotFoundError(f"task not found: {task_id}") from err

    def get_by_generation_key(self, generation_key: str) -> CareTask:
        """Return one task by deterministic generation key."""
        try:
            task_id = self._generation_keys[generation_key]
        except KeyError as err:
            raise CareTaskNotFoundError(
                f"task generation_key not found: {generation_key}"
            ) from err
        return self._tasks[task_id]

    def contains_generation_key(self, generation_key: str) -> bool:
        """Return whether a deterministic generation key is already registered."""
        return generation_key in self._generation_keys

    def all(self) -> tuple[CareTask, ...]:
        """List tasks in deterministic due-time and identifier order."""
        return tuple(self._tasks.values())

    def for_reptile(self, reptile_id: str) -> tuple[CareTask, ...]:
        """List tasks for one reptile."""
        return tuple(
            task for task in self._tasks.values() if task.reptile_id == reptile_id
        )

    def for_care_plan(self, care_plan_id: str) -> tuple[CareTask, ...]:
        """List tasks for one care plan."""
        return tuple(
            task for task in self._tasks.values() if task.care_plan_id == care_plan_id
        )

    def for_status(self, status: CareTaskStatus) -> tuple[CareTask, ...]:
        """List tasks by durable task status."""
        resolved = CareTaskStatus(status)
        return tuple(task for task in self._tasks.values() if task.status is resolved)

    def pending(self) -> tuple[CareTask, ...]:
        """List pending tasks."""
        return self.for_status(CareTaskStatus.PENDING)

    def unresolved_operations(self) -> tuple[CareTask, ...]:
        """List terminal tasks with persisted work that still needs reconciliation."""
        return tuple(
            task
            for task in self._tasks.values()
            if task.status is not CareTaskStatus.PENDING
            and task.resolution_key is not None
            and task.resolution_reconciled_at is None
        )

    def due_between(self, start: datetime, end: datetime) -> tuple[CareTask, ...]:
        """List tasks whose due time falls in the inclusive UTC interval."""
        start_time = _aware_utc_datetime(start, "start")
        end_time = _aware_utc_datetime(end, "end")
        if start_time > end_time:
            raise InvalidCareTaskError("start must not be after end")
        return tuple(
            task
            for task in self._tasks.values()
            if start_time <= task.due_at <= end_time
        )

    async def _save(self, tasks: tuple[CareTask, ...]) -> None:
        """Persist then publish a validated replacement collection."""
        validated, generation_keys = self._validated_state(tasks)
        ordered = tuple(validated.values())
        await self._persistence.async_save(ordered)
        self._tasks = validated
        self._generation_keys = generation_keys

    def _publish(self, tasks: tuple[CareTask, ...]) -> None:
        """Publish validated task and generation-key mappings together."""
        self._tasks, self._generation_keys = self._validated_state(tasks)

    def _validated_state(
        self, tasks: tuple[CareTask, ...]
    ) -> tuple[Mapping[str, CareTask], Mapping[str, str]]:
        """Validate and deterministically index task and generation-key mappings."""
        indexed: dict[str, CareTask] = {}
        generation_keys: dict[str, str] = {}
        for task in tasks:
            if not isinstance(task, CareTask):
                raise InvalidCareTaskError(
                    "repository values must be CareTask instances"
                )
            if task.task_id in indexed:
                raise DuplicateCareTaskError(f"duplicate task ID: {task.task_id}")
            if task.generation_key in generation_keys:
                raise DuplicateGenerationKeyError(
                    f"duplicate generation_key: {task.generation_key}"
                )
            self._validate_references(task)
            indexed[task.task_id] = task
            generation_keys[task.generation_key] = task.task_id

        ordered = tuple(
            sorted(indexed.values(), key=lambda item: (item.due_at, item.task_id))
        )
        ordered_indexed = {task.task_id: task for task in ordered}
        return (
            MappingProxyType(ordered_indexed),
            MappingProxyType(dict(sorted(generation_keys.items()))),
        )

    def _validate_references(self, task: CareTask) -> None:
        """Ensure referenced domain records are registered."""
        try:
            self._reptile_repository.get(task.reptile_id)
        except ReptileNotFoundError as err:
            raise UnknownTaskReptileError(
                f"unknown reptile: {task.reptile_id}"
            ) from err
        try:
            self._care_plan_repository.get(task.care_plan_id)
        except CarePlanNotFoundError as err:
            raise UnknownCarePlanReferenceError(
                f"unknown care plan: {task.care_plan_id}"
            ) from err
        try:
            self._task_templates.get(task.task_template_id)
        except TaskTemplateNotFoundError as err:
            raise UnknownTaskTemplateReferenceError(
                f"unknown task template: {task.task_template_id}"
            ) from err
        try:
            self._workflow_graphs.get(task.workflow_id)
        except WorkflowNotFoundError as err:
            raise UnknownWorkflowReferenceError(
                f"unknown workflow graph: {task.workflow_id}"
            ) from err


_CARE_TASK_REQUIRED_KEYS = frozenset(
    {
        "task_id",
        "reptile_id",
        "care_plan_id",
        "task_template_id",
        "workflow_id",
        "status",
        "created_at",
        "due_at",
        "completed_at",
        "outcome",
        "notes",
        "attachment_references",
        "generated_by",
        "parent_task_id",
        "workflow_chain_id",
        "workflow_node_id",
        "snoozed_until",
        "assigned_user_id",
        "resolution_action",
        "resolution_actor_id",
        "resolution_source",
        "environmental_context",
        "resolution_key",
        "resolution_reconciled_at",
        "generation_key",
        "generation_reason",
        "schema_version",
    }
)


def care_task_to_dict(task: CareTask) -> dict[str, Any]:
    """Serialize a CareTask to explicit JSON-compatible values."""
    return {
        "task_id": task.task_id,
        "reptile_id": task.reptile_id,
        "care_plan_id": task.care_plan_id,
        "task_template_id": task.task_template_id,
        "workflow_id": task.workflow_id,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "due_at": task.due_at.isoformat(),
        "completed_at": None
        if task.completed_at is None
        else task.completed_at.isoformat(),
        "outcome": None if task.outcome is None else task_outcome_to_dict(task.outcome),
        "notes": task.notes,
        "attachment_references": list(task.attachment_references),
        "generated_by": task.generated_by,
        "parent_task_id": task.parent_task_id,
        "workflow_chain_id": task.workflow_chain_id,
        "workflow_node_id": task.workflow_node_id,
        "snoozed_until": None
        if task.snoozed_until is None
        else task.snoozed_until.isoformat(),
        "assigned_user_id": task.assigned_user_id,
        "resolution_action": None
        if task.resolution_action is None
        else task.resolution_action.value,
        "resolution_actor_id": task.resolution_actor_id,
        "resolution_source": task.resolution_source,
        "environmental_context": _to_json_compatible(task.environmental_context),
        "resolution_key": task.resolution_key,
        "resolution_reconciled_at": None
        if task.resolution_reconciled_at is None
        else task.resolution_reconciled_at.isoformat(),
        "generation_key": task.generation_key,
        "generation_reason": task.generation_reason.value,
        "schema_version": task.schema_version,
    }


def care_task_from_dict(value: Mapping[str, Any]) -> CareTask:
    """Deserialize and strictly validate a serialized CareTask."""
    data = _mapping(value, "care task")
    schema_version = data.get("schema_version")
    if schema_version not in {1, CARE_TASK_SCHEMA_VERSION}:
        raise InvalidCareTaskError(f"unsupported schema version: {schema_version!r}")
    if schema_version == 1:
        data = dict(data)
        data.setdefault("workflow_node_id", None)
        data.setdefault("resolution_action", None)
        data.setdefault("resolution_actor_id", None)
        data.setdefault("resolution_source", None)
        data.setdefault("environmental_context", {})
        data.setdefault("resolution_key", None)
        data.setdefault("resolution_reconciled_at", None)
        data["schema_version"] = CARE_TASK_SCHEMA_VERSION
    _keys(data, _CARE_TASK_REQUIRED_KEYS, frozenset(), "care task")
    attachments = data["attachment_references"]
    if not isinstance(attachments, list):
        raise InvalidCareTaskError("attachment_references must be an array")
    outcome_value = data["outcome"]
    if outcome_value is None:
        outcome = None
    else:
        outcome_mapping = _mapping(outcome_value, "outcome")
        try:
            outcome = task_outcome_from_dict(outcome_mapping)
        except InvalidTaskOutcomeError as err:
            raise InvalidCareTaskError(str(err)) from err
    return CareTask(
        task_id=data["task_id"],
        reptile_id=data["reptile_id"],
        care_plan_id=data["care_plan_id"],
        task_template_id=data["task_template_id"],
        workflow_id=data["workflow_id"],
        status=data["status"],
        created_at=_deserialize_datetime(data["created_at"], "created_at"),
        due_at=_deserialize_datetime(data["due_at"], "due_at"),
        completed_at=_deserialize_optional_datetime(
            data["completed_at"], "completed_at"
        ),
        outcome=outcome,
        notes=data["notes"],
        attachment_references=tuple(attachments),
        generated_by=data["generated_by"],
        parent_task_id=data["parent_task_id"],
        workflow_chain_id=data["workflow_chain_id"],
        workflow_node_id=data["workflow_node_id"],
        snoozed_until=_deserialize_optional_datetime(
            data["snoozed_until"], "snoozed_until"
        ),
        assigned_user_id=data["assigned_user_id"],
        resolution_action=data["resolution_action"],
        resolution_actor_id=data["resolution_actor_id"],
        resolution_source=data["resolution_source"],
        environmental_context=data["environmental_context"],
        resolution_key=data["resolution_key"],
        resolution_reconciled_at=_deserialize_optional_datetime(
            data["resolution_reconciled_at"],
            "resolution_reconciled_at",
        ),
        generation_key=data["generation_key"],
        generation_reason=data["generation_reason"],
        schema_version=CARE_TASK_SCHEMA_VERSION,
    )


class MemoryCareTaskPersistence:
    """In-memory persistence adapter for domain tests and development."""

    def __init__(self, tasks: tuple[CareTask, ...] = ()) -> None:
        """Initialize with an immutable task collection."""
        self.tasks = tuple(tasks)

    async def async_load(self) -> tuple[CareTask, ...]:
        """Return the current in-memory collection."""
        return self.tasks

    async def async_save(self, tasks: tuple[CareTask, ...]) -> None:
        """Replace the in-memory collection."""
        self.tasks = tuple(tasks)
