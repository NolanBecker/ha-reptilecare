"""Application-layer care execution orchestration."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import logging
import math
from types import MappingProxyType
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from ..domain.care_task import (
    CareTask,
    CareTaskGenerationReason,
    CareTaskNotFoundError,
    CareTaskRepository,
    CareTaskResolutionAction,
    CareTaskStatus,
)
from ..domain.task_outcome import TaskOutcome
from ..domain.task_template import (
    CompletionBehavior,
    ContextFieldType,
    TaskContextFieldDefinition,
    TaskTemplate,
    TaskTemplateNotFoundError,
    TaskTemplateRegistry,
)
from ..domain.workflow import (
    WorkflowActionType,
    WorkflowDelay,
    WorkflowDelayUnit,
    WorkflowGraph,
    WorkflowNodeType,
    WorkflowNotFoundError,
    WorkflowRegistry,
    WorkflowTransition,
    WorkflowTriggerType,
)
from ..models import CareEvent, CareEventType
from ..storage import CareEventStore

_LOGGER = logging.getLogger(__name__)


class CareEngineError(Exception):
    """Base application-layer care execution error."""


class CareTaskResolutionNotAllowedError(CareEngineError):
    """Raised when a task cannot be resolved in its current state."""


class ConflictingTaskResolutionError(CareEngineError):
    """Raised when a second incompatible terminal resolution is requested."""


class InvalidTaskOutcomeSelectionError(CareEngineError):
    """Raised when a task outcome is missing or not permitted."""


class InvalidTaskContextError(CareEngineError):
    """Raised when structured task context fails template validation."""


class MissingTaskTemplateReferenceError(CareEngineError):
    """Raised when a task references a missing task template."""


class MissingWorkflowGraphReferenceError(CareEngineError):
    """Raised when a task references a missing workflow graph."""


class InvalidWorkflowEffectError(CareEngineError):
    """Raised when a workflow effect cannot be applied safely."""


class CareEnginePersistenceError(CareEngineError):
    """Raised when persisted task resolution cannot be fully reconciled."""


class ResolutionAction(StrEnum):
    """Terminal actions accepted by the CareEngine request model."""

    COMPLETE = "complete"
    SKIP = "skip"
    CANCEL = "cancel"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _aware_utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _json_value(value: object, name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise ValueError(f"{name} must contain only JSON-compatible values")


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    return value


def _freeze_mapping(value: object, name: str) -> Mapping[str, Any]:
    frozen = _json_value(value, name)
    if not isinstance(frozen, Mapping):
        raise ValueError(f"{name} must be an object")
    return frozen


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(_to_json_compatible(value), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class CareTaskResolutionRequest:
    """Typed terminal-resolution request independent from Home Assistant."""

    action: ResolutionAction
    outcome_id: str | None = None
    outcome_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    notes: str | None = None
    attachment_references: tuple[str, ...] = ()
    actor_id: str | None = None
    source: str | None = None
    completed_at: datetime | None = field(default_factory=lambda: datetime.now(UTC))
    environmental_context: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", ResolutionAction(self.action))
        object.__setattr__(
            self, "outcome_id", _optional_text(self.outcome_id, "outcome_id")
        )
        object.__setattr__(
            self,
            "outcome_metadata",
            _freeze_mapping(self.outcome_metadata, "outcome_metadata"),
        )
        object.__setattr__(self, "notes", _optional_text(self.notes, "notes"))
        object.__setattr__(
            self,
            "attachment_references",
            tuple(
                _text(value, "attachment_reference")
                for value in self.attachment_references
            ),
        )
        object.__setattr__(self, "actor_id", _optional_text(self.actor_id, "actor_id"))
        object.__setattr__(self, "source", _optional_text(self.source, "source"))
        completed_at = (
            self.completed_at if self.completed_at is not None else datetime.now(UTC)
        )
        object.__setattr__(
            self, "completed_at", _aware_utc(completed_at, "completed_at")
        )
        object.__setattr__(
            self,
            "environmental_context",
            _freeze_mapping(self.environmental_context, "environmental_context"),
        )


@dataclass(frozen=True, slots=True)
class CreateTaskEffect:
    """Declarative follow-up task creation effect."""

    effect_id: str
    template_id: str
    workflow_node_id: str
    delay: WorkflowDelay | None = None
    sequence_position: int = 0
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class CreateEventEffect:
    """Declarative additional CareEvent effect."""

    effect_id: str
    event_type: CareEventType
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class CompleteWorkflowEffect:
    """Declarative workflow completion effect."""

    effect_id: str


@dataclass(frozen=True, slots=True)
class NoOpEffect:
    """Declarative no-op effect when no transition matches."""

    reason: str


type WorkflowEffect = (
    CreateTaskEffect | CreateEventEffect | CompleteWorkflowEffect | NoOpEffect
)


@dataclass(frozen=True, slots=True)
class CareTaskResolutionResult:
    """Structured terminal-resolution result for callers and tests."""

    task: CareTask
    care_event: CareEvent
    created_follow_up_tasks: tuple[CareTask, ...] = ()
    existing_follow_up_tasks: tuple[CareTask, ...] = ()
    workflow_completed: bool = False
    replayed_existing_result: bool = False
    warnings: tuple[str, ...] = ()


class WorkflowEvaluator:
    """Pure workflow evaluator with no persistence side effects."""

    def __init__(self, workflow_graphs: WorkflowRegistry) -> None:
        self._workflow_graphs = workflow_graphs

    def evaluate(
        self,
        *,
        task: CareTask,
        template: TaskTemplate,
        resolution: CareTaskResolutionRequest,
    ) -> tuple[WorkflowEffect, ...]:
        """Evaluate the task's workflow graph for one terminal resolution."""
        try:
            graph = self._workflow_graphs.get(task.workflow_id)
        except WorkflowNotFoundError as err:
            raise MissingWorkflowGraphReferenceError(
                f"task {task.task_id} references missing workflow {task.workflow_id}"
            ) from err

        start_node = task.workflow_node_id or graph.start_node
        outgoing = tuple(
            transition
            for transition in graph.transitions
            if transition.from_node == start_node
        )
        matches = self._matching_transitions(outgoing, resolution)
        if not matches:
            return (
                NoOpEffect(
                    reason=f"no matching workflow transition for {task.task_id}"
                ),
            )

        effects: list[WorkflowEffect] = []
        for index, transition in enumerate(matches):
            effects.extend(
                self._effects_for_transition(
                    graph=graph,
                    transition=transition,
                    sequence_position=index,
                )
            )
        return tuple(effects)

    def _matching_transitions(
        self,
        transitions: Sequence[WorkflowTransition],
        resolution: CareTaskResolutionRequest,
    ) -> tuple[WorkflowTransition, ...]:
        explicit = tuple(
            transition
            for transition in transitions
            if transition.trigger.trigger_type is WorkflowTriggerType.OUTCOME_SELECTED
            and transition.trigger.outcome_id == resolution.outcome_id
        )
        if explicit:
            return explicit
        if resolution.action is ResolutionAction.COMPLETE:
            completed = tuple(
                transition
                for transition in transitions
                if transition.trigger.trigger_type is WorkflowTriggerType.TASK_COMPLETED
            )
            if completed:
                return completed
        return ()

    def _effects_for_transition(
        self,
        *,
        graph: WorkflowGraph,
        transition: WorkflowTransition,
        sequence_position: int,
    ) -> tuple[WorkflowEffect, ...]:
        node = next(node for node in graph.nodes if node.node_id == transition.to_node)
        if node.node_type is WorkflowNodeType.END:
            return (CompleteWorkflowEffect(effect_id=node.node_id),)
        if node.action is None:
            return (NoOpEffect(reason=f"workflow node {node.node_id} has no action"),)
        if node.action.action_type is WorkflowActionType.CREATE_TASK:
            template_id = node.action.metadata.get("template_id")
            if not isinstance(template_id, str) or not template_id.strip():
                raise InvalidWorkflowEffectError(
                    f"workflow node {node.node_id} is missing create-task template_id"
                )
            workflow_node_id = node.action.metadata.get("task_node_id", node.node_id)
            if not isinstance(workflow_node_id, str) or not workflow_node_id.strip():
                raise InvalidWorkflowEffectError(
                    f"workflow node {node.node_id} has invalid task_node_id"
                )
            return (
                CreateTaskEffect(
                    effect_id=node.node_id,
                    template_id=template_id.strip(),
                    workflow_node_id=workflow_node_id.strip(),
                    delay=transition.delay,
                    sequence_position=sequence_position,
                    metadata=_freeze_mapping(
                        node.action.metadata, "workflow effect metadata"
                    ),
                ),
            )
        if node.action.action_type is WorkflowActionType.CREATE_CARE_EVENT:
            raw_event_type = node.action.metadata.get("event_type")
            if not isinstance(raw_event_type, str):
                raise InvalidWorkflowEffectError(
                    f"workflow node {node.node_id} is missing create-event event_type"
                )
            return (
                CreateEventEffect(
                    effect_id=node.node_id,
                    event_type=CareEventType(raw_event_type),
                    metadata=_freeze_mapping(
                        node.action.metadata, "workflow event metadata"
                    ),
                ),
            )
        if node.action.action_type in {
            WorkflowActionType.DELAY,
            WorkflowActionType.COMPLETE_WORKFLOW,
            WorkflowActionType.BRANCH,
        }:
            next_transitions = tuple(
                item for item in graph.transitions if item.from_node == node.node_id
            )
            if not next_transitions:
                return (
                    NoOpEffect(
                        reason=f"workflow node {node.node_id} has no next transition"
                    ),
                )
            effects: list[WorkflowEffect] = []
            for next_index, next_transition in enumerate(next_transitions):
                effects.extend(
                    self._effects_for_transition(
                        graph=graph,
                        transition=next_transition,
                        sequence_position=next_index,
                    )
                )
            return tuple(effects)
        raise InvalidWorkflowEffectError(
            f"unsupported workflow action type {node.action.action_type.value}"
        )


class CareEngine:
    """Idempotent care execution orchestration for terminal task resolution."""

    def __init__(
        self,
        task_repository: CareTaskRepository,
        task_templates: TaskTemplateRegistry,
        workflow_graphs: WorkflowRegistry,
        event_store: CareEventStore,
        workflow_evaluator: WorkflowEvaluator,
    ) -> None:
        self._task_repository = task_repository
        self._task_templates = task_templates
        self._workflow_graphs = workflow_graphs
        self._event_store = event_store
        self._workflow_evaluator = workflow_evaluator

    async def async_reconcile_pending_operations(self) -> tuple[str, ...]:
        """Resume incomplete persisted care operations without duplicating work."""
        reconciled: list[str] = []
        for task in self._task_repository.unresolved_operations():
            try:
                await self._reconcile_task_resolution(task)
            except CareEngineError as err:
                _LOGGER.warning(
                    "Unable to reconcile task %s: %s",
                    task.task_id,
                    err,
                )
                continue
            reconciled.append(task.task_id)
        return tuple(reconciled)

    async def async_resolve_task(
        self,
        task_id: str,
        request: CareTaskResolutionRequest,
    ) -> CareTaskResolutionResult:
        """Resolve one pending CareTask and reconcile any resulting work."""
        try:
            task = self._task_repository.get(task_id)
        except CareTaskNotFoundError as err:
            raise CareTaskResolutionNotAllowedError(
                f"task not found: {task_id}"
            ) from err
        template = self._get_template(task)

        request = self._normalize_request(task, template, request)
        request_key = self._resolution_key(task, request)

        if task.status is not CareTaskStatus.PENDING:
            return await self._replay_or_raise(task, template, request, request_key)

        resolved_task = replace(
            task,
            status=self._status_for_action(request.action),
            completed_at=request.completed_at,
            outcome=None
            if request.outcome_id is None
            else TaskOutcome(
                outcome_id=request.outcome_id,
                metadata=request.outcome_metadata,
            ),
            notes=request.notes,
            attachment_references=request.attachment_references,
            workflow_node_id=task.workflow_node_id
            or self._workflow_graphs.get(task.workflow_id).start_node,
            resolution_action=CareTaskResolutionAction(request.action.value),
            resolution_actor_id=request.actor_id,
            resolution_source=request.source,
            environmental_context=request.environmental_context,
            resolution_key=request_key,
            resolution_reconciled_at=None,
        )
        await self._task_repository.async_update(resolved_task)
        return await self._reconcile_task_resolution(resolved_task)

    async def _replay_or_raise(
        self,
        task: CareTask,
        template: TaskTemplate,
        request: CareTaskResolutionRequest,
        request_key: str,
    ) -> CareTaskResolutionResult:
        if task.resolution_key is not None and task.resolution_key == request_key:
            result = await self._reconcile_task_resolution(task)
            return replace(result, replayed_existing_result=True)
        raise ConflictingTaskResolutionError(
            f"task {task.task_id} already resolved as {task.status.value}"
        )

    async def _reconcile_task_resolution(
        self,
        task: CareTask,
    ) -> CareTaskResolutionResult:
        template = self._get_template(task)
        primary_event = await self._ensure_primary_event(task, template)
        effects = self._workflow_evaluator.evaluate(
            task=task,
            template=template,
            resolution=self._request_from_task(task),
        )

        created: list[CareTask] = []
        existing: list[CareTask] = []
        workflow_completed = False
        warnings: list[str] = []

        for effect in effects:
            if isinstance(effect, CreateTaskEffect):
                follow_up, was_created = await self._ensure_follow_up_task(task, effect)
                (created if was_created else existing).append(follow_up)
            elif isinstance(effect, CreateEventEffect):
                await self._ensure_additional_event(task, effect)
            elif isinstance(effect, CompleteWorkflowEffect):
                workflow_completed = True
            elif isinstance(effect, NoOpEffect):
                warnings.append(effect.reason)

        if task.resolution_key is not None and task.resolution_reconciled_at is None:
            updated = replace(task, resolution_reconciled_at=datetime.now(UTC))
            await self._task_repository.async_update(updated)
            task = updated

        return CareTaskResolutionResult(
            task=task,
            care_event=primary_event,
            created_follow_up_tasks=tuple(created),
            existing_follow_up_tasks=tuple(existing),
            workflow_completed=workflow_completed,
            warnings=tuple(warnings),
        )

    def _normalize_request(
        self,
        task: CareTask,
        template: TaskTemplate,
        request: CareTaskResolutionRequest,
    ) -> CareTaskResolutionRequest:
        outcome_id = request.outcome_id
        if outcome_id is None:
            default_outcome = {
                ResolutionAction.SKIP: "skipped",
                ResolutionAction.CANCEL: "cancelled",
            }.get(request.action)
            if default_outcome is not None and any(
                item.outcome_id == default_outcome
                for item in template.expected_outcomes
            ):
                outcome_id = default_outcome
        if template.expected_outcomes and outcome_id is None:
            raise InvalidTaskOutcomeSelectionError(
                f"task {task.task_id} requires an outcome_id"
            )
        if outcome_id is not None and not any(
            item.outcome_id == outcome_id for item in template.expected_outcomes
        ):
            raise InvalidTaskOutcomeSelectionError(
                f"task {task.task_id} does not allow outcome {outcome_id}"
            )
        validated_metadata = self._validate_context_fields(
            task=task,
            definitions=template.context_fields,
            metadata=request.outcome_metadata,
        )
        return replace(
            request,
            outcome_id=outcome_id,
            outcome_metadata=validated_metadata,
        )

    def _validate_context_fields(
        self,
        *,
        task: CareTask,
        definitions: Sequence[TaskContextFieldDefinition],
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        known = {definition.field_id: definition for definition in definitions}
        unknown = sorted(set(metadata) - set(known))
        if unknown:
            raise InvalidTaskContextError(
                f"task {task.task_id} has unknown context fields: {', '.join(unknown)}"
            )
        missing = sorted(
            definition.field_id
            for definition in definitions
            if definition.required and definition.field_id not in metadata
        )
        if missing:
            raise InvalidTaskContextError(
                "task "
                f"{task.task_id} is missing required context fields: "
                f"{', '.join(missing)}"
            )
        validated: dict[str, Any] = {}
        for field_id, value in metadata.items():
            definition = known[field_id]
            self._validate_context_value(field_id, definition, value)
            validated[field_id] = _json_value(value, f"context field {field_id}")
        return MappingProxyType(validated)

    @staticmethod
    def _validate_context_value(
        field_id: str,
        definition: TaskContextFieldDefinition,
        value: Any,
    ) -> None:
        if definition.field_type is ContextFieldType.TEXT and not isinstance(
            value, str
        ):
            raise InvalidTaskContextError(f"context field {field_id} must be text")
        if definition.field_type is ContextFieldType.NUMBER and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))
        ):
            raise InvalidTaskContextError(f"context field {field_id} must be numeric")
        if definition.field_type is ContextFieldType.DURATION and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
        ):
            raise InvalidTaskContextError(
                f"context field {field_id} must be a non-negative duration"
            )
        if definition.field_type is ContextFieldType.PHOTO and not isinstance(
            value, str
        ):
            raise InvalidTaskContextError(
                f"context field {field_id} must be a photo reference string"
            )

    async def _ensure_primary_event(
        self,
        task: CareTask,
        template: TaskTemplate,
    ) -> CareEvent:
        event_id = self._primary_event_id(task)
        existing = await self._event_store.async_get_event(event_id)
        if existing is not None:
            return existing
        event = CareEvent(
            event_id=event_id,
            reptile_id=task.reptile_id,
            event_type=self._event_type_for_template(template.completion_behavior),
            timestamp=task.completed_at or datetime.now(UTC),
            task_id=task.task_id,
            care_plan_id=task.care_plan_id,
            outcome_id=None if task.outcome is None else task.outcome.outcome_id,
            context=MappingProxyType(
                {
                    "action": task.resolution_action.value
                    if task.resolution_action is not None
                    else task.status.value,
                    "outcome_metadata": {}
                    if task.outcome is None
                    else _to_json_compatible(task.outcome.metadata),
                    "notes": task.notes,
                }
            ),
            actor_id=task.resolution_actor_id,
            source=task.resolution_source,
            environmental_snapshot=task.environmental_context,
            attachment_references=task.attachment_references,
            metadata=MappingProxyType({"workflow_id": task.workflow_id}),
        )
        try:
            await self._event_store.async_append_event(event)
        except ValueError:
            existing = await self._event_store.async_get_event(event_id)
            if existing is None:
                raise CareEnginePersistenceError(
                    f"task {task.task_id} primary event could not be persisted"
                ) from None
            return existing
        return event

    async def _ensure_additional_event(
        self,
        task: CareTask,
        effect: CreateEventEffect,
    ) -> CareEvent:
        event_id = uuid5(
            NAMESPACE_URL,
            f"{task.resolution_key}|workflow_event|{effect.effect_id}",
        )
        existing = await self._event_store.async_get_event(event_id)
        if existing is not None:
            return existing
        event = CareEvent(
            event_id=event_id,
            reptile_id=task.reptile_id,
            event_type=effect.event_type,
            timestamp=task.completed_at or datetime.now(UTC),
            task_id=task.task_id,
            care_plan_id=task.care_plan_id,
            outcome_id=None if task.outcome is None else task.outcome.outcome_id,
            actor_id=task.resolution_actor_id,
            source=task.resolution_source,
            environmental_snapshot=task.environmental_context,
            attachment_references=task.attachment_references,
            metadata=effect.metadata,
        )
        try:
            await self._event_store.async_append_event(event)
        except ValueError:
            existing = await self._event_store.async_get_event(event_id)
            if existing is None:
                raise CareEnginePersistenceError(
                    "task "
                    f"{task.task_id} workflow event {effect.effect_id} "
                    "could not be persisted"
                ) from None
            return existing
        return event

    async def _ensure_follow_up_task(
        self,
        task: CareTask,
        effect: CreateTaskEffect,
    ) -> tuple[CareTask, bool]:
        try:
            self._task_templates.get(effect.template_id)
        except TaskTemplateNotFoundError as err:
            raise MissingTaskTemplateReferenceError(
                "task "
                f"{task.task_id} follow-up template is missing: "
                f"{effect.template_id}"
            ) from err
        generation_key = self._follow_up_generation_key(task, effect)
        if self._task_repository.contains_generation_key(generation_key):
            return self._task_repository.get_by_generation_key(generation_key), False
        due_at = self._apply_delay(task.completed_at or datetime.now(UTC), effect.delay)
        follow_up = CareTask(
            reptile_id=task.reptile_id,
            care_plan_id=task.care_plan_id,
            task_template_id=effect.template_id,
            workflow_id=task.workflow_id,
            due_at=due_at,
            generation_key=generation_key,
            created_at=task.completed_at or datetime.now(UTC),
            generated_by=f"care_engine:{task.task_id}:{effect.effect_id}",
            parent_task_id=task.task_id,
            workflow_chain_id=task.workflow_chain_id,
            workflow_node_id=effect.workflow_node_id,
            generation_reason=CareTaskGenerationReason.FOLLOW_UP,
        )
        try:
            await self._task_repository.async_add(follow_up)
        except ValueError as err:
            if self._task_repository.contains_generation_key(generation_key):
                return self._task_repository.get_by_generation_key(
                    generation_key
                ), False
            raise CareEnginePersistenceError(
                "task "
                f"{task.task_id} follow-up {effect.effect_id} "
                "could not be persisted"
            ) from err
        return follow_up, True

    def _get_template(self, task: CareTask) -> TaskTemplate:
        try:
            return self._task_templates.get(task.task_template_id)
        except TaskTemplateNotFoundError as err:
            raise MissingTaskTemplateReferenceError(
                "task "
                f"{task.task_id} references missing template "
                f"{task.task_template_id}"
            ) from err

    @staticmethod
    def _status_for_action(action: ResolutionAction) -> CareTaskStatus:
        return {
            ResolutionAction.COMPLETE: CareTaskStatus.COMPLETED,
            ResolutionAction.SKIP: CareTaskStatus.SKIPPED,
            ResolutionAction.CANCEL: CareTaskStatus.CANCELLED,
        }[action]

    @staticmethod
    def _request_from_task(task: CareTask) -> CareTaskResolutionRequest:
        return CareTaskResolutionRequest(
            action=ResolutionAction(
                CareTaskResolutionAction.COMPLETE.value
                if task.resolution_action is None
                else task.resolution_action.value
            ),
            outcome_id=None if task.outcome is None else task.outcome.outcome_id,
            outcome_metadata=(
                MappingProxyType({}) if task.outcome is None else task.outcome.metadata
            ),
            notes=task.notes,
            attachment_references=task.attachment_references,
            actor_id=task.resolution_actor_id,
            source=task.resolution_source,
            completed_at=task.completed_at or datetime.now(UTC),
            environmental_context=task.environmental_context,
        )

    @staticmethod
    def _resolution_key(task: CareTask, request: CareTaskResolutionRequest) -> str:
        payload = {
            "task_id": task.task_id,
            "action": request.action.value,
            "outcome_id": request.outcome_id,
            "outcome_metadata": _to_json_compatible(request.outcome_metadata),
            "notes": request.notes,
            "attachment_references": list(request.attachment_references),
            "actor_id": request.actor_id,
            "source": request.source,
            "completed_at": request.completed_at.isoformat(),
            "environmental_context": _to_json_compatible(request.environmental_context),
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _primary_event_id(task: CareTask) -> UUID:
        if task.resolution_key is None:
            raise CareEnginePersistenceError(
                f"task {task.task_id} is missing a persisted resolution_key"
            )
        return uuid5(NAMESPACE_URL, f"{task.resolution_key}|primary")

    @staticmethod
    def _event_type_for_template(
        completion_behavior: CompletionBehavior,
    ) -> CareEventType:
        raw_event_type = completion_behavior.metadata.get("event_type")
        if not isinstance(raw_event_type, str):
            raise InvalidWorkflowEffectError(
                "task template completion_behavior.metadata.event_type is required"
            )
        return CareEventType(raw_event_type)

    @staticmethod
    def _follow_up_generation_key(task: CareTask, effect: CreateTaskEffect) -> str:
        try:
            workflow = UUID(task.workflow_chain_id) if task.workflow_chain_id else None
        except ValueError:
            workflow = None
        seed = "|".join(
            (
                task.task_id,
                task.workflow_id,
                task.generation_key,
                effect.effect_id,
                effect.template_id,
                effect.workflow_node_id,
                str(effect.sequence_position),
                "" if workflow is None else str(workflow),
            )
        )
        return sha256(seed.encode("utf-8")).hexdigest()

    @staticmethod
    def _apply_delay(occurred_at: datetime, delay: WorkflowDelay | None) -> datetime:
        timestamp = occurred_at.astimezone(UTC)
        if delay is None:
            return timestamp
        if delay.unit is WorkflowDelayUnit.MINUTES:
            return timestamp + timedelta(minutes=delay.amount)
        if delay.unit is WorkflowDelayUnit.HOURS:
            return timestamp + timedelta(hours=delay.amount)
        if delay.unit is WorkflowDelayUnit.DAYS:
            return timestamp + timedelta(days=delay.amount)
        if delay.unit is WorkflowDelayUnit.WEEKS:
            return timestamp + timedelta(weeks=delay.amount)
        absolute_month = (timestamp.year * 12 + timestamp.month - 1) + delay.amount
        year, month_index = divmod(absolute_month, 12)
        month = month_index + 1
        day = min(timestamp.day, monthrange(year, month)[1])
        return timestamp.replace(year=year, month=month, day=day)
