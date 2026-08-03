"""Task template domain models, serialization, and registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.resources import files
from importlib.resources.abc import Traversable
import json
import math
import re
from types import MappingProxyType
from typing import Any, Self

TASK_TEMPLATE_SCHEMA_VERSION = 1
BUILTIN_TEMPLATE_PACKAGE = "custom_components.reptilecare.task_templates"
_NAMESPACED_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")
_LOCAL_ID = re.compile(r"^[a-z][a-z0-9_]*$")

type TaskTemplateScalar = str | int | float | bool | None


class TaskTemplateError(Exception):
    """Base exception for task template operations."""


class InvalidTaskTemplateError(TaskTemplateError, ValueError):
    """Raised when a task template definition is malformed or unsupported."""


class DuplicateTaskTemplateError(TaskTemplateError):
    """Raised for duplicate task template identifiers."""


class TaskTemplateNotFoundError(TaskTemplateError, LookupError):
    """Raised when a requested task template is not registered."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidTaskTemplateError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _json_value(value: object, name: str) -> Any:
    """Recursively validate JSON-compatible metadata values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidTaskTemplateError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InvalidTaskTemplateError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise InvalidTaskTemplateError(f"{name} must contain only JSON-compatible values")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidTaskTemplateError(f"{name} must be an object")
    return value


def _array(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise InvalidTaskTemplateError(f"{name} must be an array")
    return value


def _keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    name: str,
) -> None:
    if missing := required - set(value):
        raise InvalidTaskTemplateError(
            f"{name} is missing keys: {', '.join(sorted(missing))}"
        )
    if unknown := set(value) - required - optional:
        raise InvalidTaskTemplateError(
            f"{name} contains unknown keys: {', '.join(sorted(unknown))}"
        )


class TaskCategory(StrEnum):
    """Typed categories describing reusable care actions."""

    FEEDING = "feeding"
    CLEANING = "cleaning"
    HEALTH = "health"
    ENVIRONMENT = "environment"
    LIGHTING = "lighting"
    MAINTENANCE = "maintenance"
    OBSERVATION = "observation"
    MEDICATION = "medication"
    CUSTOM = "custom"


class TaskPriority(StrEnum):
    """Relative priority attached to a reusable task template."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ContextFieldType(StrEnum):
    """Supported future value kinds for structured completion context."""

    TEXT = "text"
    NUMBER = "number"
    DURATION = "duration"
    PHOTO = "photo"


@dataclass(frozen=True, slots=True)
class TaskOutcomeDefinition:
    """A reusable allowed outcome for a task template."""

    outcome_id: str
    display_name: str
    description: str | None = None

    def __post_init__(self) -> None:
        outcome_id = _text(self.outcome_id, "outcome_id")
        if _LOCAL_ID.fullmatch(outcome_id) is None:
            raise InvalidTaskTemplateError("outcome_id must be a lowercase identifier")
        object.__setattr__(self, "outcome_id", outcome_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(
            self, "description", _optional_text(self.description, "description")
        )


@dataclass(frozen=True, slots=True)
class TaskContextFieldDefinition:
    """A structured field a future completion UI may optionally request."""

    field_id: str
    display_name: str
    field_type: ContextFieldType
    description: str | None = None
    unit: str | None = None
    required: bool = False
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        field_id = _text(self.field_id, "field_id")
        if _LOCAL_ID.fullmatch(field_id) is None:
            raise InvalidTaskTemplateError("field_id must be a lowercase identifier")
        try:
            field_type = ContextFieldType(self.field_type)
        except (TypeError, ValueError) as err:
            raise InvalidTaskTemplateError("field_type is invalid") from err
        if not isinstance(self.required, bool):
            raise InvalidTaskTemplateError("required must be a boolean")
        metadata = _json_value(self.metadata, "context field metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidTaskTemplateError("context field metadata must be an object")
        object.__setattr__(self, "field_id", field_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "field_type", field_type)
        object.__setattr__(
            self, "description", _optional_text(self.description, "description")
        )
        object.__setattr__(self, "unit", _optional_text(self.unit, "unit"))
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class CompletionBehavior:
    """Descriptive placeholder for future completion side effects."""

    create_care_event: bool = True
    supports_follow_up_task: bool = False
    supports_workflow: bool = False
    workflow_graph_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        for name in (
            "create_care_event",
            "supports_follow_up_task",
            "supports_workflow",
        ):
            if not isinstance(getattr(self, name), bool):
                raise InvalidTaskTemplateError(f"{name} must be a boolean")
        metadata = _json_value(self.metadata, "completion behavior metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidTaskTemplateError(
                "completion behavior metadata must be an object"
            )
        workflow_graph_id = _optional_text(self.workflow_graph_id, "workflow_graph_id")
        if workflow_graph_id is not None:
            if _NAMESPACED_ID.fullmatch(workflow_graph_id) is None:
                raise InvalidTaskTemplateError(
                    "workflow_graph_id must be a lowercase namespaced identifier"
                )
            if not self.supports_workflow:
                raise InvalidTaskTemplateError(
                    "workflow_graph_id requires supports_workflow to be true"
                )
        object.__setattr__(self, "workflow_graph_id", workflow_graph_id)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class TaskTemplate:
    """Immutable reusable definition of a care action kind."""

    template_id: str
    display_name: str
    description: str
    category: TaskCategory
    icon: str | None = None
    expected_outcomes: tuple[TaskOutcomeDefinition, ...] = ()
    context_fields: tuple[TaskContextFieldDefinition, ...] = ()
    default_priority: TaskPriority = TaskPriority.NORMAL
    estimated_duration: int | None = None
    completion_behavior: CompletionBehavior = field(default_factory=CompletionBehavior)
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    schema_version: int = TASK_TEMPLATE_SCHEMA_VERSION
    template_version: int = 1

    def __post_init__(self) -> None:
        template_id = _text(self.template_id, "template_id")
        if _NAMESPACED_ID.fullmatch(template_id) is None:
            raise InvalidTaskTemplateError(
                "template_id must be a lowercase namespaced identifier"
            )
        for name, value in (
            ("schema_version", self.schema_version),
            ("template_version", self.template_version),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidTaskTemplateError(f"{name} must be a positive integer")
        try:
            category = TaskCategory(self.category)
        except (TypeError, ValueError) as err:
            raise InvalidTaskTemplateError("category is invalid") from err
        try:
            default_priority = TaskPriority(self.default_priority)
        except (TypeError, ValueError) as err:
            raise InvalidTaskTemplateError("default_priority is invalid") from err
        if self.estimated_duration is not None and (
            isinstance(self.estimated_duration, bool)
            or not isinstance(self.estimated_duration, int)
            or self.estimated_duration < 1
        ):
            raise InvalidTaskTemplateError(
                "estimated_duration must be a positive integer number of minutes"
            )
        if not isinstance(self.completion_behavior, CompletionBehavior):
            raise InvalidTaskTemplateError("completion_behavior has an invalid type")
        metadata = _json_value(self.metadata, "metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidTaskTemplateError("metadata must be an object")
        expected_outcomes = tuple(self.expected_outcomes)
        if not all(
            isinstance(item, TaskOutcomeDefinition) for item in expected_outcomes
        ):
            raise InvalidTaskTemplateError("expected_outcomes contain invalid values")
        if len({item.outcome_id for item in expected_outcomes}) != len(
            expected_outcomes
        ):
            raise InvalidTaskTemplateError("expected_outcome IDs must be unique")
        context_fields = tuple(self.context_fields)
        if not all(
            isinstance(item, TaskContextFieldDefinition) for item in context_fields
        ):
            raise InvalidTaskTemplateError("context_fields contain invalid values")
        if len({item.field_id for item in context_fields}) != len(context_fields):
            raise InvalidTaskTemplateError("context field IDs must be unique")

        object.__setattr__(self, "template_id", template_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "description", _text(self.description, "description"))
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "icon", _optional_text(self.icon, "icon"))
        object.__setattr__(self, "expected_outcomes", expected_outcomes)
        object.__setattr__(self, "context_fields", context_fields)
        object.__setattr__(self, "default_priority", default_priority)
        object.__setattr__(self, "metadata", metadata)


_TEMPLATE_REQUIRED_KEYS = frozenset(
    {
        "template_id",
        "display_name",
        "description",
        "category",
        "expected_outcomes",
        "context_fields",
        "default_priority",
        "completion_behavior",
        "metadata",
        "schema_version",
        "template_version",
    }
)
_TEMPLATE_OPTIONAL_KEYS = frozenset({"icon", "estimated_duration"})
_OUTCOME_REQUIRED_KEYS = frozenset({"outcome_id", "display_name"})
_OUTCOME_OPTIONAL_KEYS = frozenset({"description"})
_CONTEXT_FIELD_REQUIRED_KEYS = frozenset({"field_id", "display_name", "field_type"})
_CONTEXT_FIELD_OPTIONAL_KEYS = frozenset(
    {"description", "unit", "required", "metadata"}
)
_COMPLETION_BEHAVIOR_REQUIRED_KEYS = frozenset(
    {"create_care_event", "supports_follow_up_task", "supports_workflow", "metadata"}
)


def task_template_to_dict(template: TaskTemplate) -> dict[str, Any]:
    """Serialize a task template to JSON-compatible values."""
    expected_outcomes = []
    for outcome in template.expected_outcomes:
        item: dict[str, Any] = {
            "outcome_id": outcome.outcome_id,
            "display_name": outcome.display_name,
        }
        if outcome.description is not None:
            item["description"] = outcome.description
        expected_outcomes.append(item)

    context_fields = []
    for field_definition in template.context_fields:
        item: dict[str, Any] = {
            "field_id": field_definition.field_id,
            "display_name": field_definition.display_name,
            "field_type": field_definition.field_type.value,
            "required": field_definition.required,
            "metadata": _to_json_compatible(field_definition.metadata),
        }
        if field_definition.description is not None:
            item["description"] = field_definition.description
        if field_definition.unit is not None:
            item["unit"] = field_definition.unit
        context_fields.append(item)

    return {
        "template_id": template.template_id,
        "display_name": template.display_name,
        "description": template.description,
        "category": template.category.value,
        "icon": template.icon,
        "expected_outcomes": expected_outcomes,
        "context_fields": context_fields,
        "default_priority": template.default_priority.value,
        "estimated_duration": template.estimated_duration,
        "completion_behavior": {
            "create_care_event": template.completion_behavior.create_care_event,
            "supports_follow_up_task": (
                template.completion_behavior.supports_follow_up_task
            ),
            "supports_workflow": template.completion_behavior.supports_workflow,
            "workflow_graph_id": template.completion_behavior.workflow_graph_id,
            "metadata": _to_json_compatible(template.completion_behavior.metadata),
        },
        "metadata": _to_json_compatible(template.metadata),
        "schema_version": template.schema_version,
        "template_version": template.template_version,
    }


def _to_json_compatible(value: Any) -> Any:
    """Convert immutable metadata containers back to JSON-compatible values."""
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    return value


def task_template_from_dict(value: Mapping[str, Any]) -> TaskTemplate:
    """Deserialize and strictly validate a task template mapping."""
    data = _mapping(value, "task template")
    _keys(data, _TEMPLATE_REQUIRED_KEYS, _TEMPLATE_OPTIONAL_KEYS, "task template")
    if data["schema_version"] != TASK_TEMPLATE_SCHEMA_VERSION:
        raise InvalidTaskTemplateError(
            f"unsupported schema version: {data['schema_version']!r}"
        )

    expected_outcomes = []
    for index, raw in enumerate(_array(data["expected_outcomes"], "expected_outcomes")):
        item = _mapping(raw, f"expected outcome {index}")
        _keys(
            item,
            _OUTCOME_REQUIRED_KEYS,
            _OUTCOME_OPTIONAL_KEYS,
            f"expected outcome {index}",
        )
        expected_outcomes.append(
            TaskOutcomeDefinition(
                outcome_id=item["outcome_id"],
                display_name=item["display_name"],
                description=item.get("description"),
            )
        )

    context_fields = []
    for index, raw in enumerate(_array(data["context_fields"], "context_fields")):
        item = _mapping(raw, f"context field {index}")
        _keys(
            item,
            _CONTEXT_FIELD_REQUIRED_KEYS,
            _CONTEXT_FIELD_OPTIONAL_KEYS,
            f"context field {index}",
        )
        context_fields.append(
            TaskContextFieldDefinition(
                field_id=item["field_id"],
                display_name=item["display_name"],
                field_type=item["field_type"],
                description=item.get("description"),
                unit=item.get("unit"),
                required=item.get("required", False),
                metadata=item.get("metadata", {}),
            )
        )

    completion_behavior = _mapping(data["completion_behavior"], "completion_behavior")
    _keys(
        completion_behavior,
        _COMPLETION_BEHAVIOR_REQUIRED_KEYS,
        frozenset({"workflow_graph_id"}),
        "completion_behavior",
    )

    return TaskTemplate(
        template_id=data["template_id"],
        display_name=data["display_name"],
        description=data["description"],
        category=data["category"],
        icon=data.get("icon"),
        expected_outcomes=tuple(expected_outcomes),
        context_fields=tuple(context_fields),
        default_priority=data["default_priority"],
        estimated_duration=data.get("estimated_duration"),
        completion_behavior=CompletionBehavior(
            create_care_event=completion_behavior["create_care_event"],
            supports_follow_up_task=completion_behavior["supports_follow_up_task"],
            supports_workflow=completion_behavior["supports_workflow"],
            workflow_graph_id=completion_behavior.get("workflow_graph_id"),
            metadata=completion_behavior["metadata"],
        ),
        metadata=data["metadata"],
        schema_version=data["schema_version"],
        template_version=data["template_version"],
    )


class TaskTemplateRegistry:
    """Immutable lookup registry for validated task templates."""

    def __init__(self, templates: Iterable[TaskTemplate] = ()) -> None:
        registered: dict[str, TaskTemplate] = {}
        for template in templates:
            if not isinstance(template, TaskTemplate):
                raise InvalidTaskTemplateError(
                    "registry values must be TaskTemplate instances"
                )
            if template.template_id in registered:
                raise DuplicateTaskTemplateError(
                    f"duplicate task template ID: {template.template_id}"
                )
            registered[template.template_id] = template
        self._templates: Mapping[str, TaskTemplate] = MappingProxyType(
            dict(sorted(registered.items()))
        )

    @classmethod
    def from_files(cls, template_files: Iterable[Traversable]) -> Self:
        """Load task templates from JSON files."""
        templates = []
        for template_file in sorted(template_files, key=lambda item: item.name):
            try:
                raw = json.loads(template_file.read_text(encoding="utf-8"))
                templates.append(
                    task_template_from_dict(_mapping(raw, template_file.name))
                )
            except (OSError, json.JSONDecodeError, TaskTemplateError) as err:
                raise InvalidTaskTemplateError(
                    f"unable to load {template_file.name}: {err}"
                ) from err
        return cls(templates)

    @classmethod
    def load_builtin_templates(cls) -> Self:
        """Load all bundled task templates from package resources."""
        directory = files(BUILTIN_TEMPLATE_PACKAGE)
        return cls.from_files(
            item
            for item in directory.iterdir()
            if item.is_file() and item.name.endswith(".json")
        )

    def get(self, template_id: str) -> TaskTemplate:
        """Return one registered task template."""
        try:
            return self._templates[template_id]
        except KeyError as err:
            raise TaskTemplateNotFoundError(
                f"task template not found: {template_id}"
            ) from err

    def all(self) -> tuple[TaskTemplate, ...]:
        """Return templates in deterministic identifier order."""
        return tuple(self._templates.values())

    def contains(self, template_id: str) -> bool:
        """Return whether a template is registered."""
        return template_id in self._templates
