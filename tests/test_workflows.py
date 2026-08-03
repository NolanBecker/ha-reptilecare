"""Tests for workflow graph domain models and serialization."""

from dataclasses import FrozenInstanceError
import json

import pytest

from custom_components.reptilecare.domain.workflow import (
    InvalidWorkflowError,
    WorkflowActionDefinition,
    WorkflowActionType,
    WorkflowDelay,
    WorkflowDelayUnit,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowTransition,
    WorkflowTrigger,
    WorkflowTriggerType,
    workflow_graph_from_dict,
    workflow_graph_to_dict,
)


def _graph() -> WorkflowGraph:
    return WorkflowGraph(
        workflow_id="builtin:feeding_cycle",
        display_name="Feeding Cycle",
        description="Describe follow-up care after a successful feeding.",
        version=1,
        start_node="start",
        nodes=(
            WorkflowNode("start", WorkflowNodeType.START),
            WorkflowNode(
                "record_event",
                WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.CREATE_CARE_EVENT,
                    display_name="Record Feeding Event",
                    metadata={"event_type": "feeding"},
                ),
            ),
            WorkflowNode(
                "create_task",
                WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.CREATE_TASK,
                    display_name="Create Next Feeding Task",
                    metadata={"template_id": "builtin:feed_fruit"},
                ),
            ),
            WorkflowNode("complete", WorkflowNodeType.END),
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="record_event",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.OUTCOME_SELECTED,
                    outcome_id="ate_normally",
                ),
            ),
            WorkflowTransition(
                from_node="record_event",
                to_node="create_task",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.TIMEOUT_ELAPSED,
                ),
                delay=WorkflowDelay(amount=24, unit=WorkflowDelayUnit.HOURS),
            ),
            WorkflowTransition(
                from_node="create_task",
                to_node="complete",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.TASK_COMPLETED,
                ),
            ),
        ),
        metadata={"audience": "core"},
    )


def test_workflow_graph_is_immutable_and_normalized() -> None:
    """Workflow graphs freeze node collections and identifiers."""
    nodes = [
        WorkflowNode("start", WorkflowNodeType.START),
        WorkflowNode("complete", WorkflowNodeType.END),
    ]
    graph = WorkflowGraph(
        workflow_id="builtin:minimal",
        display_name=" Minimal ",
        description=" Description ",
        version=1,
        start_node="start",
        nodes=(
            nodes[0],
            WorkflowNode(
                "run",
                WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.COMPLETE_WORKFLOW,
                    display_name="Complete Workflow",
                ),
            ),
            nodes[1],
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="run",
                trigger=WorkflowTrigger(WorkflowTriggerType.MANUAL_TRIGGER),
            ),
            WorkflowTransition(
                from_node="run",
                to_node="complete",
                trigger=WorkflowTrigger(WorkflowTriggerType.TASK_COMPLETED),
            ),
        ),
    )
    nodes.append(WorkflowNode("orphan", WorkflowNodeType.END))
    assert graph.display_name == "Minimal"
    assert len(graph.nodes) == 3
    with pytest.raises(FrozenInstanceError):
        graph.display_name = "Changed"  # type: ignore[misc]


def test_workflow_graph_rejects_invalid_values() -> None:
    """Workflow models reject malformed IDs, triggers, and delay values."""
    with pytest.raises(InvalidWorkflowError, match="workflow_id"):
        WorkflowGraph(
            workflow_id="feeding_cycle",
            display_name="Bad",
            description="Bad",
            version=1,
            start_node="start",
            nodes=(
                WorkflowNode("start", WorkflowNodeType.START),
                WorkflowNode("done", WorkflowNodeType.END),
            ),
            transitions=(
                WorkflowTransition(
                    from_node="start",
                    to_node="done",
                    trigger=WorkflowTrigger(WorkflowTriggerType.MANUAL_TRIGGER),
                ),
            ),
        )

    with pytest.raises(InvalidWorkflowError, match="outcome_id"):
        WorkflowTrigger(
            trigger_type=WorkflowTriggerType.OUTCOME_SELECTED,
            outcome_id="Not Valid",
        )

    with pytest.raises(InvalidWorkflowError, match="delay amount"):
        WorkflowDelay(amount=0, unit=WorkflowDelayUnit.HOURS)


def test_workflow_graph_rejects_invalid_transitions_and_orphans() -> None:
    """Graph validation catches missing nodes, orphan nodes, and bad ends."""
    base = _graph()

    with pytest.raises(InvalidWorkflowError, match="unknown to_node"):
        WorkflowGraph(
            workflow_id=base.workflow_id,
            display_name=base.display_name,
            description=base.description,
            version=base.version,
            start_node=base.start_node,
            nodes=base.nodes,
            transitions=(
                WorkflowTransition(
                    from_node="start",
                    to_node="missing",
                    trigger=WorkflowTrigger(WorkflowTriggerType.MANUAL_TRIGGER),
                ),
            ),
            metadata=base.metadata,
        )

    with pytest.raises(InvalidWorkflowError, match="orphan nodes"):
        WorkflowGraph(
            workflow_id="builtin:with_orphan",
            display_name=base.display_name,
            description=base.description,
            version=base.version,
            start_node=base.start_node,
            nodes=base.nodes + (WorkflowNode("orphan", WorkflowNodeType.END),),
            transitions=base.transitions,
            metadata=base.metadata,
        )

    with pytest.raises(InvalidWorkflowError, match="end nodes must not have outgoing"):
        WorkflowGraph(
            workflow_id="builtin:bad_end",
            display_name="Bad End",
            description="Bad end",
            version=1,
            start_node="start",
            nodes=(
                WorkflowNode("start", WorkflowNodeType.START),
                WorkflowNode(
                    "run",
                    WorkflowNodeType.ACTION,
                    action=WorkflowActionDefinition(
                        action_type=WorkflowActionType.BRANCH,
                        display_name="Branch",
                    ),
                ),
                WorkflowNode("done", WorkflowNodeType.END),
            ),
            transitions=(
                WorkflowTransition(
                    from_node="start",
                    to_node="done",
                    trigger=WorkflowTrigger(WorkflowTriggerType.MANUAL_TRIGGER),
                ),
                WorkflowTransition(
                    from_node="done",
                    to_node="run",
                    trigger=WorkflowTrigger(WorkflowTriggerType.MANUAL_TRIGGER),
                ),
                WorkflowTransition(
                    from_node="run",
                    to_node="done",
                    trigger=WorkflowTrigger(WorkflowTriggerType.TASK_COMPLETED),
                ),
            ),
        )


def test_workflow_graph_serialization_round_trip_is_json_compatible() -> None:
    """Workflow graphs serialize cleanly through JSON."""
    graph = _graph()
    serialized = workflow_graph_to_dict(graph)
    assert serialized["transitions"][1]["delay"] == {"amount": 24, "unit": "hours"}
    assert workflow_graph_from_dict(json.loads(json.dumps(serialized))) == graph


def test_workflow_graph_deserialization_rejects_invalid_documents() -> None:
    """Strict deserialization rejects malformed workflow documents."""
    data = workflow_graph_to_dict(_graph())
    data["unknown"] = True
    with pytest.raises(InvalidWorkflowError, match="unknown keys"):
        workflow_graph_from_dict(data)

    data = workflow_graph_to_dict(_graph())
    data["schema_version"] = 2
    with pytest.raises(InvalidWorkflowError, match="unsupported schema"):
        workflow_graph_from_dict(data)

    data = workflow_graph_to_dict(_graph())
    data["nodes"][0]["unexpected"] = True
    with pytest.raises(InvalidWorkflowError, match="unknown keys"):
        workflow_graph_from_dict(data)
