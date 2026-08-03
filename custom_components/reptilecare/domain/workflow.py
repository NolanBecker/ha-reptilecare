"""Workflow graph domain models, serialization, and registry."""

from __future__ import annotations

from collections import deque
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

WORKFLOW_SCHEMA_VERSION = 1
BUILTIN_WORKFLOW_PACKAGE = "custom_components.reptilecare.workflows"
_NAMESPACED_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")
_LOCAL_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class WorkflowError(Exception):
    """Base exception for workflow graph operations."""


class InvalidWorkflowError(WorkflowError, ValueError):
    """Raised when a workflow graph definition is malformed or unsupported."""


class DuplicateWorkflowError(WorkflowError):
    """Raised for duplicate workflow identifiers."""


class WorkflowNotFoundError(WorkflowError, LookupError):
    """Raised when a requested workflow graph is not registered."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidWorkflowError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _json_value(value: object, name: str) -> Any:
    """Recursively validate JSON-compatible metadata values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidWorkflowError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InvalidWorkflowError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise InvalidWorkflowError(f"{name} must contain only JSON-compatible values")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidWorkflowError(f"{name} must be an object")
    return value


def _array(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise InvalidWorkflowError(f"{name} must be an array")
    return value


def _keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    name: str,
) -> None:
    if missing := required - set(value):
        raise InvalidWorkflowError(
            f"{name} is missing keys: {', '.join(sorted(missing))}"
        )
    if unknown := set(value) - required - optional:
        raise InvalidWorkflowError(
            f"{name} contains unknown keys: {', '.join(sorted(unknown))}"
        )


class WorkflowNodeType(StrEnum):
    """Typed workflow node roles."""

    START = "start"
    ACTION = "action"
    DECISION = "decision"
    END = "end"


class WorkflowTriggerType(StrEnum):
    """Typed transition trigger definitions."""

    TASK_COMPLETED = "task_completed"
    OUTCOME_SELECTED = "outcome_selected"
    TIMEOUT_ELAPSED = "timeout_elapsed"
    MANUAL_TRIGGER = "manual_trigger"


class WorkflowActionType(StrEnum):
    """Typed descriptive actions a future workflow service may interpret."""

    CREATE_CARE_EVENT = "create_care_event"
    CREATE_TASK = "create_task"
    COMPLETE_WORKFLOW = "complete_workflow"
    DELAY = "delay"
    BRANCH = "branch"


class WorkflowDelayUnit(StrEnum):
    """Typed structural delay units for workflow transitions."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


@dataclass(frozen=True, slots=True)
class WorkflowDelay:
    """A structural delay definition for future scheduling logic."""

    amount: int
    unit: WorkflowDelayUnit

    def __post_init__(self) -> None:
        if (
            isinstance(self.amount, bool)
            or not isinstance(self.amount, int)
            or self.amount < 1
        ):
            raise InvalidWorkflowError("delay amount must be a positive integer")
        try:
            unit = WorkflowDelayUnit(self.unit)
        except (TypeError, ValueError) as err:
            raise InvalidWorkflowError("delay unit is invalid") from err
        object.__setattr__(self, "unit", unit)


@dataclass(frozen=True, slots=True)
class WorkflowTrigger:
    """A trigger definition that allows a transition to fire later."""

    trigger_type: WorkflowTriggerType
    outcome_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        try:
            trigger_type = WorkflowTriggerType(self.trigger_type)
        except (TypeError, ValueError) as err:
            raise InvalidWorkflowError("trigger_type is invalid") from err
        outcome_id = _optional_text(self.outcome_id, "outcome_id")
        if trigger_type is WorkflowTriggerType.OUTCOME_SELECTED:
            if outcome_id is None or _LOCAL_ID.fullmatch(outcome_id) is None:
                raise InvalidWorkflowError(
                    "outcome_selected triggers require a lowercase outcome_id"
                )
        elif outcome_id is not None:
            raise InvalidWorkflowError(
                "only outcome_selected triggers may define outcome_id"
            )
        metadata = _json_value(self.metadata, "trigger metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidWorkflowError("trigger metadata must be an object")
        object.__setattr__(self, "trigger_type", trigger_type)
        object.__setattr__(self, "outcome_id", outcome_id)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class WorkflowCondition:
    """A structural placeholder for future conditional branching."""

    condition_id: str
    description: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        condition_id = _text(self.condition_id, "condition_id")
        if _LOCAL_ID.fullmatch(condition_id) is None:
            raise InvalidWorkflowError("condition_id must be a lowercase identifier")
        metadata = _json_value(self.metadata, "condition metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidWorkflowError("condition metadata must be an object")
        object.__setattr__(self, "condition_id", condition_id)
        object.__setattr__(
            self, "description", _optional_text(self.description, "description")
        )
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class WorkflowActionDefinition:
    """A descriptive action attached to an action node."""

    action_type: WorkflowActionType
    display_name: str
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        try:
            action_type = WorkflowActionType(self.action_type)
        except (TypeError, ValueError) as err:
            raise InvalidWorkflowError("action_type is invalid") from err
        metadata = _json_value(self.metadata, "action metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidWorkflowError("action metadata must be an object")
        object.__setattr__(self, "action_type", action_type)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """An immutable node in a reusable workflow graph."""

    node_id: str
    node_type: WorkflowNodeType
    action: WorkflowActionDefinition | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        node_id = _text(self.node_id, "node_id")
        if _LOCAL_ID.fullmatch(node_id) is None:
            raise InvalidWorkflowError("node_id must be a lowercase identifier")
        try:
            node_type = WorkflowNodeType(self.node_type)
        except (TypeError, ValueError) as err:
            raise InvalidWorkflowError("node_type is invalid") from err
        if node_type is WorkflowNodeType.ACTION:
            if not isinstance(self.action, WorkflowActionDefinition):
                raise InvalidWorkflowError("action nodes require an action definition")
        elif self.action is not None:
            raise InvalidWorkflowError("only action nodes may define an action")
        metadata = _json_value(self.metadata, "node metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidWorkflowError("node metadata must be an object")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "node_type", node_type)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class WorkflowTransition:
    """A structural edge connecting two nodes in a workflow graph."""

    from_node: str
    to_node: str
    trigger: WorkflowTrigger
    condition: WorkflowCondition | None = None
    delay: WorkflowDelay | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        from_node = _text(self.from_node, "from_node")
        to_node = _text(self.to_node, "to_node")
        for name, value in (("from_node", from_node), ("to_node", to_node)):
            if _LOCAL_ID.fullmatch(value) is None:
                raise InvalidWorkflowError(f"{name} must be a lowercase identifier")
        if not isinstance(self.trigger, WorkflowTrigger):
            raise InvalidWorkflowError("trigger has an invalid type")
        if self.condition is not None and not isinstance(
            self.condition, WorkflowCondition
        ):
            raise InvalidWorkflowError("condition has an invalid type")
        if self.delay is not None and not isinstance(self.delay, WorkflowDelay):
            raise InvalidWorkflowError("delay has an invalid type")
        metadata = _json_value(self.metadata, "transition metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidWorkflowError("transition metadata must be an object")
        object.__setattr__(self, "from_node", from_node)
        object.__setattr__(self, "to_node", to_node)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """An immutable reusable graph describing post-outcome behavior."""

    workflow_id: str
    display_name: str
    description: str
    version: int
    start_node: str
    nodes: tuple[WorkflowNode, ...]
    transitions: tuple[WorkflowTransition, ...]
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    schema_version: int = WORKFLOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        workflow_id = _text(self.workflow_id, "workflow_id")
        if _NAMESPACED_ID.fullmatch(workflow_id) is None:
            raise InvalidWorkflowError(
                "workflow_id must be a lowercase namespaced identifier"
            )
        for name, value in (
            ("version", self.version),
            ("schema_version", self.schema_version),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidWorkflowError(f"{name} must be a positive integer")
        start_node = _text(self.start_node, "start_node")
        if _LOCAL_ID.fullmatch(start_node) is None:
            raise InvalidWorkflowError("start_node must be a lowercase identifier")
        nodes = tuple(self.nodes)
        if not nodes or not all(isinstance(node, WorkflowNode) for node in nodes):
            raise InvalidWorkflowError("nodes must contain WorkflowNode instances")
        transitions = tuple(self.transitions)
        if not all(
            isinstance(transition, WorkflowTransition) for transition in transitions
        ):
            raise InvalidWorkflowError(
                "transitions must contain WorkflowTransition instances"
            )
        metadata = _json_value(self.metadata, "metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidWorkflowError("metadata must be an object")

        node_index: dict[str, WorkflowNode] = {}
        for node in nodes:
            if node.node_id in node_index:
                raise InvalidWorkflowError("workflow node IDs must be unique")
            node_index[node.node_id] = node
        if start_node not in node_index:
            raise InvalidWorkflowError("start_node must reference a registered node")
        if node_index[start_node].node_type is not WorkflowNodeType.START:
            raise InvalidWorkflowError("start_node must reference a start node")

        incoming: dict[str, int] = dict.fromkeys(node_index, 0)
        outgoing: dict[str, int] = dict.fromkeys(node_index, 0)
        for transition in transitions:
            if transition.from_node not in node_index:
                raise InvalidWorkflowError(
                    f"transition references unknown from_node: {transition.from_node}"
                )
            if transition.to_node not in node_index:
                raise InvalidWorkflowError(
                    f"transition references unknown to_node: {transition.to_node}"
                )
            incoming[transition.to_node] += 1
            outgoing[transition.from_node] += 1

        if incoming[start_node] != 0:
            raise InvalidWorkflowError("start node must not have incoming transitions")

        end_nodes = [
            node
            for node in node_index.values()
            if node.node_type is WorkflowNodeType.END
        ]
        if not end_nodes:
            raise InvalidWorkflowError("workflow must contain at least one end node")
        for end_node in end_nodes:
            if outgoing[end_node.node_id] != 0:
                raise InvalidWorkflowError(
                    "end nodes must not have outgoing transitions"
                )
        for node in node_index.values():
            if (
                node.node_type is not WorkflowNodeType.END
                and outgoing[node.node_id] == 0
            ):
                raise InvalidWorkflowError(
                    f"non-end node has no outgoing transitions: {node.node_id}"
                )

        reachable = self._reachable_nodes(start_node, transitions)
        if reachable != set(node_index):
            orphaned = sorted(set(node_index) - reachable)
            raise InvalidWorkflowError(
                f"workflow contains orphan nodes: {', '.join(orphaned)}"
            )

        object.__setattr__(self, "workflow_id", workflow_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "description", _text(self.description, "description"))
        object.__setattr__(self, "start_node", start_node)
        object.__setattr__(
            self,
            "nodes",
            tuple(sorted(nodes, key=lambda item: item.node_id)),
        )
        object.__setattr__(
            self,
            "transitions",
            tuple(
                sorted(
                    transitions,
                    key=lambda item: (
                        item.from_node,
                        item.to_node,
                        item.trigger.trigger_type.value,
                    ),
                )
            ),
        )
        object.__setattr__(self, "metadata", metadata)

    @staticmethod
    def _reachable_nodes(
        start_node: str, transitions: tuple[WorkflowTransition, ...]
    ) -> set[str]:
        adjacency: dict[str, list[str]] = {}
        for transition in transitions:
            adjacency.setdefault(transition.from_node, []).append(transition.to_node)
        queue: deque[str] = deque((start_node,))
        visited: set[str] = set()
        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            queue.extend(adjacency.get(node_id, ()))
        return visited


_GRAPH_REQUIRED_KEYS = frozenset(
    {
        "workflow_id",
        "display_name",
        "description",
        "version",
        "start_node",
        "nodes",
        "transitions",
        "metadata",
        "schema_version",
    }
)
_NODE_REQUIRED_KEYS = frozenset({"node_id", "node_type"})
_NODE_OPTIONAL_KEYS = frozenset({"action", "metadata"})
_ACTION_REQUIRED_KEYS = frozenset({"action_type", "display_name", "metadata"})
_TRIGGER_REQUIRED_KEYS = frozenset({"trigger_type", "metadata"})
_TRIGGER_OPTIONAL_KEYS = frozenset({"outcome_id"})
_TRANSITION_REQUIRED_KEYS = frozenset({"from_node", "to_node", "trigger"})
_TRANSITION_OPTIONAL_KEYS = frozenset({"condition", "delay", "metadata"})
_CONDITION_REQUIRED_KEYS = frozenset({"condition_id", "metadata"})
_CONDITION_OPTIONAL_KEYS = frozenset({"description"})
_DELAY_REQUIRED_KEYS = frozenset({"amount", "unit"})


def workflow_graph_to_dict(graph: WorkflowGraph) -> dict[str, Any]:
    """Serialize a workflow graph to JSON-compatible values."""
    return {
        "workflow_id": graph.workflow_id,
        "display_name": graph.display_name,
        "description": graph.description,
        "version": graph.version,
        "start_node": graph.start_node,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type.value,
                "action": None
                if node.action is None
                else {
                    "action_type": node.action.action_type.value,
                    "display_name": node.action.display_name,
                    "metadata": _to_json_compatible(node.action.metadata),
                },
                "metadata": _to_json_compatible(node.metadata),
            }
            for node in graph.nodes
        ],
        "transitions": [
            {
                "from_node": transition.from_node,
                "to_node": transition.to_node,
                "trigger": {
                    "trigger_type": transition.trigger.trigger_type.value,
                    "outcome_id": transition.trigger.outcome_id,
                    "metadata": _to_json_compatible(transition.trigger.metadata),
                },
                "condition": None
                if transition.condition is None
                else {
                    "condition_id": transition.condition.condition_id,
                    "description": transition.condition.description,
                    "metadata": _to_json_compatible(transition.condition.metadata),
                },
                "delay": None
                if transition.delay is None
                else {
                    "amount": transition.delay.amount,
                    "unit": transition.delay.unit.value,
                },
                "metadata": _to_json_compatible(transition.metadata),
            }
            for transition in graph.transitions
        ],
        "metadata": _to_json_compatible(graph.metadata),
        "schema_version": graph.schema_version,
    }


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    return value


def workflow_graph_from_dict(value: Mapping[str, Any]) -> WorkflowGraph:
    """Deserialize and strictly validate a workflow graph mapping."""
    data = _mapping(value, "workflow graph")
    _keys(data, _GRAPH_REQUIRED_KEYS, frozenset(), "workflow graph")
    if data["schema_version"] != WORKFLOW_SCHEMA_VERSION:
        raise InvalidWorkflowError(
            f"unsupported schema version: {data['schema_version']!r}"
        )

    nodes = []
    for index, raw in enumerate(_array(data["nodes"], "nodes")):
        item = _mapping(raw, f"node {index}")
        _keys(item, _NODE_REQUIRED_KEYS, _NODE_OPTIONAL_KEYS, f"node {index}")
        raw_action = item.get("action")
        if raw_action is None:
            action = None
        else:
            action_item = _mapping(raw_action, f"node {index}.action")
            _keys(
                action_item,
                _ACTION_REQUIRED_KEYS,
                frozenset(),
                f"node {index}.action",
            )
            action = WorkflowActionDefinition(
                action_type=action_item["action_type"],
                display_name=action_item["display_name"],
                metadata=action_item["metadata"],
            )
        nodes.append(
            WorkflowNode(
                node_id=item["node_id"],
                node_type=item["node_type"],
                action=action,
                metadata=item.get("metadata", {}),
            )
        )

    transitions = []
    for index, raw in enumerate(_array(data["transitions"], "transitions")):
        item = _mapping(raw, f"transition {index}")
        _keys(
            item,
            _TRANSITION_REQUIRED_KEYS,
            _TRANSITION_OPTIONAL_KEYS,
            f"transition {index}",
        )
        trigger_item = _mapping(item["trigger"], f"transition {index}.trigger")
        _keys(
            trigger_item,
            _TRIGGER_REQUIRED_KEYS,
            _TRIGGER_OPTIONAL_KEYS,
            f"transition {index}.trigger",
        )
        raw_condition = item.get("condition")
        if raw_condition is None:
            condition = None
        else:
            condition_item = _mapping(raw_condition, f"transition {index}.condition")
            _keys(
                condition_item,
                _CONDITION_REQUIRED_KEYS,
                _CONDITION_OPTIONAL_KEYS,
                f"transition {index}.condition",
            )
            condition = WorkflowCondition(
                condition_id=condition_item["condition_id"],
                description=condition_item.get("description"),
                metadata=condition_item["metadata"],
            )
        raw_delay = item.get("delay")
        if raw_delay is None:
            delay = None
        else:
            delay_item = _mapping(raw_delay, f"transition {index}.delay")
            _keys(
                delay_item,
                _DELAY_REQUIRED_KEYS,
                frozenset(),
                f"transition {index}.delay",
            )
            delay = WorkflowDelay(
                amount=delay_item["amount"],
                unit=delay_item["unit"],
            )
        transitions.append(
            WorkflowTransition(
                from_node=item["from_node"],
                to_node=item["to_node"],
                trigger=WorkflowTrigger(
                    trigger_type=trigger_item["trigger_type"],
                    outcome_id=trigger_item.get("outcome_id"),
                    metadata=trigger_item["metadata"],
                ),
                condition=condition,
                delay=delay,
                metadata=item.get("metadata", {}),
            )
        )

    return WorkflowGraph(
        workflow_id=data["workflow_id"],
        display_name=data["display_name"],
        description=data["description"],
        version=data["version"],
        start_node=data["start_node"],
        nodes=tuple(nodes),
        transitions=tuple(transitions),
        metadata=data["metadata"],
        schema_version=data["schema_version"],
    )


class WorkflowRegistry:
    """Immutable lookup registry for validated workflow graphs."""

    def __init__(self, workflows: Iterable[WorkflowGraph] = ()) -> None:
        registered: dict[str, WorkflowGraph] = {}
        for workflow in workflows:
            if not isinstance(workflow, WorkflowGraph):
                raise InvalidWorkflowError(
                    "registry values must be WorkflowGraph instances"
                )
            if workflow.workflow_id in registered:
                raise DuplicateWorkflowError(
                    f"duplicate workflow ID: {workflow.workflow_id}"
                )
            registered[workflow.workflow_id] = workflow
        self._workflows: Mapping[str, WorkflowGraph] = MappingProxyType(
            dict(sorted(registered.items()))
        )

    @classmethod
    def from_files(cls, workflow_files: Iterable[Traversable]) -> Self:
        """Load workflow graphs from JSON files."""
        workflows = []
        for workflow_file in sorted(workflow_files, key=lambda item: item.name):
            try:
                raw = json.loads(workflow_file.read_text(encoding="utf-8"))
                workflows.append(
                    workflow_graph_from_dict(_mapping(raw, workflow_file.name))
                )
            except (OSError, json.JSONDecodeError, WorkflowError) as err:
                raise InvalidWorkflowError(
                    f"unable to load {workflow_file.name}: {err}"
                ) from err
        return cls(workflows)

    @classmethod
    def load_builtin_workflows(cls) -> Self:
        """Load all bundled workflow graphs from package resources."""
        directory = files(BUILTIN_WORKFLOW_PACKAGE)
        return cls.from_files(
            item
            for item in directory.iterdir()
            if item.is_file() and item.name.endswith(".json")
        )

    def get(self, workflow_id: str) -> WorkflowGraph:
        """Return one registered workflow graph."""
        try:
            return self._workflows[workflow_id]
        except KeyError as err:
            raise WorkflowNotFoundError(
                f"workflow graph not found: {workflow_id}"
            ) from err

    def all(self) -> tuple[WorkflowGraph, ...]:
        """Return workflow graphs in deterministic identifier order."""
        return tuple(self._workflows.values())

    def contains(self, workflow_id: str) -> bool:
        """Return whether a workflow graph is registered."""
        return workflow_id in self._workflows
